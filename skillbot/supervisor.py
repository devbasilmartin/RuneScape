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
- With profiles, it also runs the account rotation (rotation.py): at the end of a turn,
  or on a `skillbot switch` request, the bot hands over (finishes its load, logs out),
  and the next account's bot starts and logs in. An account whose bot stops by itself
  (plan complete, out of supplies) is benched and the rotation moves on.
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

    def __init__(self, config_path: str, data_dir: Path, profile: str | None = None):
        self.config_path = config_path
        self.data_dir = data_dir
        self.profile = profile
        self.goals = None               # goals file for the current rotation turn

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def start_client(self):
        return subprocess.Popen(["bash", str(REPO_DIR / "scripts/vm/start-client.sh")],
                                start_new_session=True)

    def start_bot(self):
        target = ["--profile", self.profile] if self.profile else ["-c", str(self.config_path)]
        goals = ["--goals", self.goals] if self.goals else []
        return subprocess.Popen([sys.executable, "-m", "skillbot", *target, "run", *goals],
                                cwd=REPO_DIR, start_new_session=True)

    def logout(self, profile: str) -> None:
        """Log the game out (does nothing if it already is)."""
        try:
            subprocess.run([sys.executable, "-m", "skillbot", "--profile", profile, "logout"],
                           cwd=REPO_DIR, timeout=180, check=False)
        except subprocess.TimeoutExpired:
            log.warning("logout timed out")

    def use_profile(self, profiles, name: str) -> None:
        profiles.use(name)
        self.profile = name
        self.data_dir = profiles.dir / name / "data"
        self.config_path = str(profiles.dir / name / "config.yaml")

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
    def __init__(self, cfg: SupervisorConfig, host, data_dir: Path, notify=notify,
                 rotation=None):
        self.cfg = cfg
        self.host = host
        self.data_dir = Path(data_dir)
        self.notify = notify
        self.rotation = rotation        # rotation.Rotation, when profiles are in use
        self.handover = None            # (next profile, hours, deadline) while handing over
        self.idle = False               # nobody's turn (all capped or benched)
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
        if self.rotation is not None:
            result = self.rotation_check()
            if result is not None:
                return result
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
                return self.stopped_by_itself()
            self.restart_bot(f"the bot crashed (exit code {code})")
        elif self.hung():
            self.restart_bot(f"no heartbeat for {self.cfg.heartbeat_minutes} min")
        elif self.frozen():
            self.restart_all(f"the screen hasn't changed for {self.cfg.freeze_minutes} min")
        return True

    def run(self) -> int:
        log.info("supervisor starting")
        try:
            self.begin_rotation()
            self.start_everything()
            while True:
                self.host.sleep(self.cfg.poll_seconds)
                if not self.check():
                    return 0
        except GiveUp as e:
            self.notify(f"supervisor gave up: {e}")
            self.stop_bot()
            return 0       # deliberate stop: systemd must not restart us


    # ---- account rotation --------------------------------------------------------------
    @property
    def profile(self):
        return self.host.profile

    def begin_rotation(self) -> None:
        """At startup: keep the current turn if it's still valid, else start the next."""
        rot = self.rotation
        if rot is None or rot.cfg is None:
            return
        now, state = self.host.now(), rot.state()
        current = state.get("current")
        eligible = [t.profile for t in rot.eligible(now)]
        if current in eligible and not rot.due(now):
            if current != self.profile:
                self.host.use_profile(rot.profiles, current)
                self.data_dir = self.host.data_dir
            return
        nxt = rot.next(now, current)
        if nxt is None:
            self.idle = True
            self.notify("rotation: nobody's turn (every account is benched or at its daily cap)")
            return
        if nxt.profile != self.profile:
            self.host.use_profile(rot.profiles, nxt.profile)
            self.data_dir = self.host.data_dir
        self.host.goals = nxt.goals
        rot.started(nxt.profile, now, nxt.hours)

    def rotation_check(self):
        """Rotation's part of a watchdog pass: None to carry on with the usual checks."""
        rot, h = self.rotation, self.host
        now = h.now()
        if self.handover is not None:
            target, hours, goals, deadline = self.handover
            if self.running(self.bot) and now < deadline:
                return True                      # still finishing its load
            if self.running(self.bot):
                log.warning("the bot didn't hand over in time; stopping it")
            self.stop_bot()
            self.handover = None
            self.switch_to(target, hours, goals)
            return True
        if self.paused:
            return None
        req = rot.take_request()
        if req:
            turn = rot.cfg.turn(req["profile"]) if rot.cfg else None
            hours = req.get("hours") or (turn.hours if turn else None)
            goals = turn.goals if turn else None
            if req["profile"] == self.profile and not self.idle:
                rot.started(self.profile, now, hours)          # just a new turn length
                return None
            self.begin_handover(req["profile"], hours, goals)
            return True
        if rot.cfg is None:
            return None
        if self.idle:
            nxt = rot.next(now, None)
            if nxt is None:
                return True                      # still nobody's turn
            self.idle = False
            self.switch_to(nxt.profile, nxt.hours, nxt.goals)
            return True
        turn = rot.cfg.turn(self.profile)
        capped = (turn is not None and turn.max_hours_per_day
                  and rot.hours_today(self.profile, now) >= turn.max_hours_per_day)
        if rot.due(now) or capped:
            nxt = rot.next(now, self.profile)
            if nxt is not None and nxt.profile == self.profile and not capped:
                rot.started(self.profile, now, nxt.hours)      # only one left: keep going
                return None
            if nxt is None:
                self.begin_handover(None, None, None)
            else:
                self.begin_handover(nxt.profile, nxt.hours, nxt.goals)
            return True
        return None

    def begin_handover(self, target, hours, goals) -> None:
        log.info("rotation: handing over from %s to %s", self.profile, target)
        if not self.running(self.bot):
            self.stop_bot()
            self.switch_to(target, hours, goals)
            return
        (self.data_dir / "handover").write_text("")
        deadline = self.host.now() + self.rotation_cfg_minutes() * 60
        self.handover = (target, hours, goals, deadline)

    def rotation_cfg_minutes(self) -> float:
        cfg = self.rotation.cfg
        return cfg.handover_minutes if cfg else 10.0

    def switch_to(self, target, hours, goals) -> None:
        """The old bot is stopped: log out, change profile, start the next bot."""
        rot, h = self.rotation, self.host
        old = self.profile
        (self.data_dir / "handover").unlink(missing_ok=True)
        if self.running(self.client):
            h.logout(old)
        if target is None:
            self.idle = True
            self.notify(f"rotation: {old} logged out; nobody's turn now (every account is "
                        "benched or at its daily cap)")
            return
        h.use_profile(rot.profiles, target)
        h.goals = goals
        self.data_dir = h.data_dir
        rot.started(target, h.now(), hours)
        self.notify(f"rotation: {old} → {target}"
                    + (f" for {hours:g}h" if hours else ""))
        gap = rot.cfg.gap_minutes if rot.cfg else 0
        if gap:
            h.sleep(gap * 60)
        if not self.running(self.client):
            self.restart_all("client not running at a switch")
        elif not self.paused:
            self.start_bot()

    def stopped_by_itself(self) -> bool:
        """The bot exited with code 0. Without a rotation, or when you stopped it, the
        supervisor exits; otherwise the account is benched and the next one goes on."""
        try:
            info = json.loads((self.data_dir / "stopped.json").read_text())
        except (OSError, ValueError):
            info = {}
        kind, detail = info.get("kind"), info.get("detail") or "no reason recorded"
        rot = self.rotation
        if rot is None or rot.cfg is None or kind in ("failsafe", "interrupt"):
            self.notify("the bot stopped by itself (see data/skillbot.log); supervisor exiting")
            return False
        self.bot = None
        if kind != "handover":
            rot.bench(self.profile, detail)
            self.notify(f"rotation: {self.profile} stopped ({detail}); benched until "
                        f"`skillbot rotation unbench {self.profile}`")
        nxt = rot.next(self.host.now(), self.profile)
        if nxt is None:
            if self.running(self.client):
                self.host.logout(self.profile)
            self.notify("rotation: no account left to play; supervisor exiting")
            return False
        self.switch_to(nxt.profile, nxt.hours, nxt.goals)
        return True
