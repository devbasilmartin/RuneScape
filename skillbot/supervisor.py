"""Keeps RuneLite and the bot running unattended.

- Starts the client, waits for its window, moves it to a fixed position (so the
  calibrated canvas origin stays valid), then starts the bot.
- Restarts the bot if it crashes (non-zero exit) or hangs (no heartbeat), and
  restarts both if the client exits or its screen freezes.
- A bot that stops by itself (exit code 0: plan finished, a setting said stop, the
  mouse-corner failsafe) is left stopped, and so is the supervisor.
- At most ``max_restarts_per_hour`` restarts; after that it gives up and notifies.
- ``skillbot pause`` / ``resume`` (a flag file) stop the bot and the watchdog so you
  can play, and start the bot again afterwards.
"""
import collections
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

from .heartbeat import last_beat
from .layout import CANVAS_H, CANVAS_W
from .notify import notify

log = logging.getLogger("skillbot")

REPO_DIR = Path(__file__).resolve().parent.parent


@dataclass
class SupervisorConfig:
    poll_seconds: float = 15
    heartbeat_minutes: float = 3          # bot counts as hung after this long without a beat
    freeze_minutes: float = 5             # client counts as frozen after this long unchanged
    max_restarts_per_hour: int = 5
    client_start_timeout: float = 180     # seconds to wait for the client window
    client_settle_seconds: float = 30     # then this long for it to finish loading
    window_name: str = "RuneLite"
    window_position: tuple = (0, 0)

    @classmethod
    def from_dict(cls, d: dict | None) -> "SupervisorConfig":
        d = dict(d or {})
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown supervisor keys: {sorted(unknown)}")
        if "window_position" in d:
            d["window_position"] = tuple(d["window_position"])
        return cls(**d)


class GiveUp(RuntimeError):
    pass


class Host:
    """The real machine: processes, the client window, the screen."""

    def __init__(self, config_path: str, data_dir: Path):
        self.config_path = config_path
        self.data_dir = data_dir

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def start_client(self):
        return subprocess.Popen(["bash", str(REPO_DIR / "scripts/vm/start-client.sh")],
                                start_new_session=True)

    def start_bot(self):
        return subprocess.Popen([sys.executable, "-m", "skillbot", "-c", self.config_path, "run"],
                                cwd=REPO_DIR, start_new_session=True)

    def stop(self, proc) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        except ProcessLookupError:
            pass

    def release_keys(self) -> None:
        # a bot killed mid shift-click must not leave shift held down
        subprocess.run(["xdotool", "keyup", "shift", "ctrl", "alt"], check=False)

    def window_exists(self, name: str) -> bool:
        return subprocess.run(["xdotool", "search", "--name", name],
                              capture_output=True).returncode == 0

    def move_window(self, name: str, x: int, y: int) -> None:
        subprocess.run(["xdotool", "search", "--name", name, "windowmove", str(x), str(y),
                        "windowactivate"], check=False)

    def grab(self):
        """The game canvas if calibrated, otherwise the whole screen."""
        import mss
        origin_file = self.data_dir / "origin.json"
        with mss.mss() as sct:
            if origin_file.exists():
                x, y = json.loads(origin_file.read_text())["origin"]
                box = {"left": x, "top": y, "width": CANVAS_W, "height": CANVAS_H}
            else:
                box = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            return np.asarray(sct.grab(box))[..., :3]


class Supervisor:
    def __init__(self, cfg: SupervisorConfig, host, data_dir: Path, notify=notify):
        self.cfg = cfg
        self.host = host
        self.data_dir = Path(data_dir)
        self.notify = notify
        self.client = None
        self.bot = None
        self.bot_started = 0.0
        self.restarts = collections.deque()
        self.last_frame = None
        self.last_change = 0.0
        self.was_paused = False

    # ---- state -------------------------------------------------------------------------
    @property
    def paused(self) -> bool:
        return (self.data_dir / "paused").exists()

    @staticmethod
    def running(proc) -> bool:
        return proc is not None and proc.poll() is None

    def _count_restart(self, reason: str) -> None:
        now = self.host.now()
        while self.restarts and now - self.restarts[0] > 3600:
            self.restarts.popleft()
        if len(self.restarts) >= self.cfg.max_restarts_per_hour:
            raise GiveUp(f"{len(self.restarts)} restarts in the last hour; last reason: {reason}")
        self.restarts.append(now)
        log.warning("restarting: %s", reason)

    # ---- starting and stopping ---------------------------------------------------------
    def start_client(self) -> None:
        h = self.host
        self.client = h.start_client()
        deadline = h.now() + self.cfg.client_start_timeout
        while not h.window_exists(self.cfg.window_name):
            if h.now() >= deadline or not self.running(self.client):
                raise RuntimeError("the client window never appeared")
            h.sleep(2)
        h.sleep(self.cfg.client_settle_seconds)
        h.move_window(self.cfg.window_name, *self.cfg.window_position)
        log.info("client started")

    def start_bot(self) -> None:
        self.bot = self.host.start_bot()
        self.bot_started = self.host.now()
        self.last_frame, self.last_change = None, self.host.now()
        log.info("bot started")

    def stop_bot(self) -> None:
        self.host.stop(self.bot)
        self.host.release_keys()
        self.bot = None

    def stop_all(self) -> None:
        self.stop_bot()
        self.host.stop(self.client)
        self.client = None

    def restart_bot(self, reason: str) -> None:
        self._count_restart(reason)
        self.stop_bot()
        self.start_bot()

    def restart_all(self, reason: str) -> None:
        self._count_restart(reason)
        self.stop_all()
        self.host.sleep(5)
        self.start_everything()

    def start_everything(self) -> None:
        """Start the client and the bot, retrying (within the restart budget) on failure."""
        while True:
            try:
                self.start_client()
                break
            except RuntimeError as e:
                self.host.stop(self.client)
                self._count_restart(str(e))
                self.host.sleep(30)
        if not self.paused:
            self.start_bot()

    # ---- watchdog ----------------------------------------------------------------------
    def hung(self) -> bool:
        beat = last_beat(self.data_dir / "heartbeat.json")
        latest = max(beat or 0.0, self.bot_started)
        return self.host.now() - latest > self.cfg.heartbeat_minutes * 60

    def frozen(self) -> bool:
        frame = self.host.grab()
        now = self.host.now()
        if frame is None:
            return False
        small = np.asarray(frame)[::4, ::4].astype(np.int16)
        if self.last_frame is None or np.abs(small - self.last_frame).mean() > 0.3:
            self.last_change = now
        self.last_frame = small
        return now - self.last_change > self.cfg.freeze_minutes * 60

    def check(self) -> bool:
        """One watchdog pass. Returns False when the supervisor should exit."""
        if self.paused:
            if self.running(self.bot):
                log.info("paused: stopping the bot")
                self.stop_bot()
            self.was_paused = True
            return True
        if self.was_paused:
            self.was_paused = False
            log.info("resumed")
            if not self.running(self.client):
                self.restart_all("client was closed while paused")
            else:
                self.start_bot()
            return True
        if not self.running(self.client):
            self.restart_all("the client exited")
        elif not self.running(self.bot):
            code = self.bot.returncode if self.bot is not None else None
            if code == 0:
                self.notify("the bot stopped by itself (see data/skillbot.log); "
                            "supervisor exiting")
                return False
            self.restart_bot(f"the bot crashed (exit code {code})")
        elif self.hung():
            self.restart_bot(f"no heartbeat for {self.cfg.heartbeat_minutes} min")
        elif self.frozen():
            self.restart_all(f"the screen hasn't changed for {self.cfg.freeze_minutes} min")
        return True

    def run(self) -> int:
        log.info("supervisor starting")
        try:
            self.start_everything()
            while True:
                self.host.sleep(self.cfg.poll_seconds)
                if not self.check():
                    return 0
        except GiveUp as e:
            self.notify(f"supervisor gave up: {e}")
            self.stop_bot()
            return 0       # deliberate stop: systemd must not restart us
