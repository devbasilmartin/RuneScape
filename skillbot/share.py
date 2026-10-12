"""Send to PC (docs/file-sharing.md): copy what Claude needs to see into the VirtualBox
shared folder, so it shows up on the PC at once.

Each send is a folder `skillbot/<time>/` in the share with:
- screen.png: the whole VM screen right now
- the bot's images (debug.png, calibrate.png, frames.png from a recording, ...)
- skillbot-log.txt: the end of the bot's log
- panel-output.txt: what the control panel's Output shows
Only the newest KEEP sends are kept.
"""
import os
import shutil
import time
from pathlib import Path

KEEP = 10
LOG_LINES = 300
IMAGES = ("debug.png", "debug-skills.png", "calibrate.png", "skills-check.png",
          "energy-check.png", "frames.png")


def find_share() -> Path | None:
    """SKILLBOT_SHARE, else ~/share, else the one VirtualBox shared folder (/media/sf_*)."""
    env = os.environ.get("SKILLBOT_SHARE", "").strip()
    candidates = [Path(env).expanduser()] if env else []
    candidates.append(Path.home() / "share")
    candidates += sorted(Path("/media").glob("sf_*"))
    for c in candidates:
        if c.is_dir() and os.access(c, os.W_OK):
            return c
    return None


def tail(path: Path, n: int) -> str:
    try:
        return "".join(path.read_text(errors="replace").splitlines(keepends=True)[-n:])
    except OSError:
        return ""


def send(repo_dir: Path, data_dir: Path, output_lines=(), dest: Path | None = None,
         screenshot=None, now=None) -> tuple[Path, list[str]]:
    """Copy everything into a new folder in the share; returns (folder, file names)."""
    dest = dest or find_share()
    if dest is None:
        raise ValueError("no shared folder: run scripts/vm/share.sh (docs/file-sharing.md)")
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
    folder = Path(dest) / "skillbot" / stamp
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    png = (screenshot or screen_png)()
    if png:
        (folder / "screen.png").write_bytes(png)
        files.append("screen.png")
    for name in IMAGES:
        if (Path(repo_dir) / name).exists():
            shutil.copyfile(Path(repo_dir) / name, folder / name)
            files.append(name)
    log = tail(Path(data_dir) / "skillbot.log", LOG_LINES)
    if log:
        (folder / "skillbot-log.txt").write_text(log)
        files.append("skillbot-log.txt")
    if output_lines:
        (folder / "panel-output.txt").write_text("\n".join(output_lines) + "\n")
        files.append("panel-output.txt")
    for old in sorted(p for p in folder.parent.iterdir() if p.is_dir())[:-KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return folder, files


def screen_png() -> bytes | None:
    """The whole VM screen as PNG (None where there is no screen, e.g. in tests)."""
    try:
        import cv2
        from .screen import grab_desktop
        img, _ = grab_desktop()
        ok, buf = cv2.imencode(".png", img[..., ::-1])
        return buf.tobytes() if ok else None
    except Exception:          # no display: send the rest anyway
        return None
