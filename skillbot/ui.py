"""`skillbot ui`: a local web page with a button for every command (docs/ui.md).

The page runs the same commands you'd type, one at a time (they share the screen and the
mouse), shows their output live, has a box for answering their questions, and shows the
images they write (debug.png, calibrate.png...). Only whitelisted commands run, and the
server only listens on this machine.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .status import snapshot

REPO_DIR = Path(__file__).resolve().parent.parent
IMAGES = ("debug.png", "debug-skills.png", "calibrate.png", "skills-check.png",
          "energy-check.png")
MAX_LINES = 2000


def actions(steps: list[str], exports: list[str]) -> dict:
    """name -> function(params) -> argv. Parameters are checked against what exists."""
    sb = [sys.executable, "-u", "-m", "skillbot"]

    def step(p):
        if p.get("step") not in steps:
            raise ValueError("pick a step from the list")
        return sb + ["check-setup", p["step"]]

    def profile(p):
        src = p.get("export") or ""
        if src and src not in exports:
            raise ValueError("pick an export from the list")
        return sb + ["runelite-profile"] + (["--from", src] if src else [])

    def origin(p):
        x, y = int(p.get("x", "")), int(p.get("y", ""))
        return sb + ["calibrate", "--origin", str(x), str(y)]

    plain = {
        "update": ["git", "pull"],
        "run_watched": sb + ["run", "--supervised"],
        "run": sb + ["run"],
        "pause": sb + ["pause"],
        "resume": sb + ["resume"],
        "calibrate": sb + ["calibrate"],
        "debug": sb + ["debug"],
        "debug_skills": sb + ["debug", "--skills", "--out", "debug-skills.png"],
        "doctor": sb + ["doctor"],
        "levels": sb + ["levels"],
        "learn_digits": sb + ["learn-digits"],
        "calibrate_run": sb + ["calibrate-run"],
        "learn_energy": sb + ["learn-energy"],
        "plan": sb + ["plan"],
        "accounts": sb + ["accounts"],
    }
    out = {name: (lambda p, argv=argv: argv) for name, argv in plain.items()}
    out.update(check_setup=step, runelite_profile=profile, calibrate_origin=origin)
    return out


class Job:
    """One running command: its output lines, and a way to answer or stop it."""

    def __init__(self, job_id: int, name: str, argv: list[str], cwd: Path):
        self.id, self.name, self.argv = job_id, name, argv
        self.lines: list[str] = []
        self.partial = ""                # the line being written (or a question)
        self.started = time.time()
        self.proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1, start_new_session=True,
                                     env={**os.environ, "PYTHONUNBUFFERED": "1"})
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        # read characters, not lines: a question ("type the energy: ") has no newline,
        # so the unfinished line is kept apart and shown as it is
        while True:
            ch = self.proc.stdout.read(1)
            if not ch:
                break
            if ch == "\n":
                self._add(self.partial)
                self.partial = ""
            else:
                self.partial += ch
        if self.partial:
            self._add(self.partial)
            self.partial = ""

    def _add(self, line: str):
        self.lines.append(line)
        del self.lines[:-MAX_LINES]

    @property
    def running(self) -> bool:
        return self.proc.poll() is None

    def send(self, text: str) -> None:
        if self.running:
            self._add(f"{self.partial}> {text}" if self.partial else f"> {text}")
            self.partial = ""
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()

    def stop(self) -> None:
        """Ctrl+C first (commands save what they learned), then terminate."""
        if not self.running:
            return
        os.killpg(self.proc.pid, signal.SIGINT)
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGTERM)

    def state(self) -> dict:
        return {"id": self.id, "name": self.name, "running": self.running,
                "returncode": self.proc.poll(),
                "lines": self.lines[-400:] + ([self.partial] if self.partial else []),
                "started": self.started}


class App:
    def __init__(self, data_dir: Path, steps: list[str], cwd: Path = REPO_DIR, levels=None):
        self.data_dir, self.steps, self.cwd = Path(data_dir), steps, Path(cwd)
        self.job: Job | None = None
        self.next_id = 1
        self.lock = threading.Lock()

    def exports(self) -> list[str]:
        """RuneLite profile exports to recolor from: the repo folder and RuneLite's own."""
        found = []
        for folder in (self.cwd, Path.home(), Path.home() / "Downloads",
                       Path.home() / ".runelite" / "profiles2"):
            for p in sorted(folder.glob("*.properties")) if folder.is_dir() else []:
                if p.name != "bot-profile.properties":
                    found.append(str(p))
        return found

    def start(self, name: str, params: dict) -> Job:
        acts = actions(self.steps, self.exports())
        if name not in acts:
            raise ValueError(f"unknown action {name!r}")
        argv = acts[name](params)
        with self.lock:
            if self.job is not None and self.job.running:
                raise ValueError(f"{self.job.name} is still running: stop it first")
            self.job = Job(self.next_id, name, argv, self.cwd)
            self.next_id += 1
        for line in params.get("answers") or []:     # e.g. learn-digits, filled in a form
            self.job.send(str(line))
        return self.job

    def state(self) -> dict:
        snap = snapshot(self.data_dir)
        images = [{"name": n, "mtime": (self.cwd / n).stat().st_mtime}
                  for n in IMAGES if (self.cwd / n).exists()]
        return {"job": self.job.state() if self.job else None, "status": snap["status"],
                "paused": snap["paused"], "heartbeat_age": snap["heartbeat_age"],
                "levels": snap["levels"], "images": images, "steps": self.steps,
                "exports": self.exports()}


def make_handler(app: App):
    page = (Path(__file__).parent / "ui.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):             # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data).encode())

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, page, "text/html; charset=utf-8")
            if path == "/api/state":
                return self._json(200, app.state())
            if path.startswith("/img/") and path[5:] in IMAGES:
                f = app.cwd / path[5:]
                if f.exists():
                    return self._send(200, f.read_bytes(), "image/png")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json(400, {"error": "bad request"})
            try:
                if self.path == "/api/start":
                    job = app.start(body.get("action", ""), body.get("params") or {})
                    return self._json(200, {"id": job.id})
                if self.path == "/api/send":
                    if app.job:
                        app.job.send(str(body.get("text", "")))
                    return self._json(200, {})
                if self.path == "/api/stop":
                    if app.job:
                        threading.Thread(target=app.job.stop, daemon=True).start()
                    return self._json(200, {})
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            self._json(404, {"error": "not found"})

    return Handler


def serve(app: App, port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"skillbot UI at {url} (Ctrl+C here to close it)")
    if open_browser:
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if app.job:
            app.job.stop()


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Skillbot
Comment=Control panel for the bot
Exec=bash -c 'cd "{repo}" && "{python}" -m skillbot ui'
Icon=utilities-terminal
Terminal=false
Categories=Utility;
"""


def install_shortcut() -> Path:
    """An app-grid entry (and a desktop icon) that opens the UI, no terminal needed."""
    entry = DESKTOP_ENTRY.format(repo=REPO_DIR, python=sys.executable)
    apps = Path.home() / ".local" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    path = apps / "skillbot.desktop"
    path.write_text(entry)
    path.chmod(0o755)
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        icon = desktop / "skillbot.desktop"
        icon.write_text(entry)
        icon.chmod(0o755)
        subprocess.run(["gio", "set", str(icon), "metadata::trusted", "true"],
                       capture_output=True)
    return path
