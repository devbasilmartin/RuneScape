"""The Discord service's logic, kept free of discord.py so it can be tested: commands,
uptime tracking, the daily summary, and mapping replies to questions."""
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

from .messages import Mailbox, _read, _write
from .status import build_summary, format_levels, format_status, snapshot

SERVICE = "skillbot.service"
PANEL = "http://127.0.0.1:8765"         # the control panel (skillbot ui) on the VM
LOG_TIME = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")


NO_PANEL = ("The control panel isn't open on the VM. /run goes through it: open Skillbot "
            "there and leave it open.")


def count_log_lines(path: Path, needle: str, since: float) -> int:
    """Lines containing ``needle`` logged after ``since`` (logs start with a timestamp)."""
    count = 0
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return 0
    for line in lines:
        m = LOG_TIME.match(line)
        if not m or needle not in line:
            continue
        when = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
        if when >= since:
            count += 1
    return count


def panel_post(path: str, body: dict) -> tuple[bool, dict]:
    """POST to the control panel: (ok, its JSON). Raises OSError when it isn't open."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(PANEL + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return False, json.loads(e.read() or b"{}")


class DiscordCore:
    def __init__(self, data_dir: Path, summary_hour: int = 9, run=subprocess.run,
                 clock=time.time, profiles=None, pricewatch=None, post=panel_post):
        self.data_dir = Path(data_dir)      # shared: the mailbox and this service's state
        self.profiles = profiles
        self.pricewatch = pricewatch
        self.mailbox = Mailbox(self.data_dir, clock=clock)
        self.summary_hour = summary_hour
        self.run = run
        self.post = post
        self.clock = clock
        self.state_path = self.data_dir / "discord" / "state.json"
        self.state = _read(self.state_path) or {"online": [], "asks_by_message": {},
                                                 "last_summary": None, "levels_then": {}}

    @property
    def status_dir(self) -> Path:
        """The data folder of the account being run (the active profile, if any)."""
        if self.profiles is not None and (name := self.profiles.active()):
            return self.profiles.dir / name / "data"
        return self.data_dir

    def save(self) -> None:
        _write(self.state_path, self.state)

    # ---- supervisor control ------------------------------------------------------------
    def supervisor_state(self) -> str:
        try:
            out = self.run(["systemctl", "--user", "is-active", SERVICE],
                           capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        return out.stdout.strip() or "unknown"

    def command(self, name: str) -> str:
        """Handle a slash command (except /screenshot, which needs the screen)."""
        data = self.status_dir
        if name == "status":
            return format_status(snapshot(data, self.clock()), self.supervisor_state())
        if name == "levels":
            return format_levels(snapshot(data, self.clock())["levels"])
        if name == "pause":
            (data / "paused").write_text("")
            return "Paused: the bot stops within ~15s. Switch RuneLite to your own profile to play."
        if name == "resume":
            (data / "paused").unlink(missing_ok=True)
            return "Resumed: switch RuneLite back to the `bot` profile; the bot starts within ~15s."
        if name in ("start", "stop"):
            out = self.run(["systemctl", "--user", name, SERVICE],
                           capture_output=True, text=True, timeout=60)
            if out.returncode != 0:
                return f"`systemctl --user {name}` failed: {out.stderr.strip()[:300]}"
            return f"Supervisor {'started' if name == 'start' else 'stopped'}."
        if name == "profile":
            if self.profiles is None or not self.profiles.names():
                return "No profiles set up (single account)."
            active = self.profiles.active()
            return "\n".join(("**→ " + n + "**") if n == active else n
                             for n in self.profiles.names())
        if name == "shopping":
            if self.pricewatch is None:
                return "Prices aren't set up."
            return self.pricewatch.shopping()
        if name == "accounts":
            if self.profiles is None or not self.profiles.names():
                return "No profiles set up (single account)."
            from .rotation import format_overview, load_rotation, overview
            return format_overview(overview(self.profiles, load_rotation(self.profiles),
                                            self.clock()), self.clock())
        if name == "questions":
            asks = self.mailbox.open_asks()
            if not asks:
                return "No open questions."
            return "\n".join(f"• {a['question']}" for a in asks)
        return f"Unknown command {name!r}."

    # ---- the control panel -------------------------------------------------------------
    def run_activity(self, method: str, minutes: float | None = None,
                     when_full: str | None = None, watching: bool = False) -> str:
        """Start one activity in the control panel, as its One activity tab does, so it
        shows in the panel's Output and its Stop works."""
        params = {"method": method, "watching": watching}
        if minutes:
            params["minutes"] = minutes
        if when_full:
            params["when_full"] = when_full
        try:
            ok, data = self.post("/api/start", {"action": "run_activity", "params": params})
        except OSError:
            return NO_PANEL
        if not ok:
            return f"Didn't start: {data.get('error', 'the panel said no')}."
        how = ("you're watching" if watching else
               "unattended: activities still experimental are skipped")
        return (f"Started **{method}**" + (f" for {minutes:g} min" if minutes else "")
                + f" ({how}). `/screenshot` to look, `/stoprun` to stop.")

    def stop_run(self) -> str:
        try:
            self.post("/api/stop", {})
        except OSError:
            return NO_PANEL
        return "Stopping what the panel is running (like its Stop button)."

    def switch(self, name: str) -> str:
        """Switch account: a clean handover when the supervisor runs, else just make
        ``name`` the active profile."""
        if self.profiles is None:
            return "No profiles set up (single account)."
        state = self.supervisor_state()
        if state == "active":
            from .rotation import load_rotation
            try:
                load_rotation(self.profiles).request(name)
            except ValueError as e:
                return str(e)
            return (f"Switching to **{name}**: the bot finishes its load and logs out, then "
                    f"{name} logs in.")
        try:
            self.profiles.use(name)
        except ValueError as e:
            return str(e)
        return f"Switched to **{name}**. The supervisor isn't running; /start to start it."

    def sold(self, item: str) -> str:
        """You sold an item: stop counting it towards sell alerts."""
        from .prices import Ledger
        Ledger(self.status_dir / "ledger.json").sold(item)
        return f"OK, {item} cleared from the ledger."

    def price_tick(self) -> list[str]:
        """Hourly: poll prices and return any alerts. Network errors are logged and skipped."""
        if self.pricewatch is None or not self.pricewatch.due():
            return []
        try:
            return self.pricewatch.run()
        except OSError as e:
            import logging
            logging.getLogger("skillbot").warning("price poll failed: %s", e)
            self.pricewatch.prices.last_poll = self.clock()
            return []

    # ---- questions ---------------------------------------------------------------------
    def remember_ask_message(self, message_id: int, ask_id: str) -> None:
        self.state["asks_by_message"][str(message_id)] = ask_id
        self.save()

    def answer_by_reply(self, replied_message_id: int, text: str) -> str | None:
        """Your reply to a question message. Returns a confirmation, or None if the
        replied-to message isn't an open question."""
        ask_id = self.state["asks_by_message"].get(str(replied_message_id))
        if ask_id is None:
            return None
        if not self.mailbox.reply(ask_id, text.strip()):
            return "That question was already answered."
        self.state["asks_by_message"].pop(str(replied_message_id), None)
        self.save()
        return f"Got it: {text.strip()}"

    def answer_by_button(self, ask_id: str, index: int) -> str:
        asks = {a["id"]: a for a in self.mailbox.open_asks()}
        ask = asks.get(ask_id)
        if ask is None or not 0 <= index < len(ask["options"]):
            return "That question was already answered."
        choice = ask["options"][index]
        self.mailbox.reply(ask_id, choice)
        return f"Got it: {choice}"

    # ---- uptime and the daily summary --------------------------------------------------
    def tick(self) -> str | None:
        """Call about once a minute. Records uptime; returns the daily summary when due."""
        now = self.clock()
        snap = snapshot(self.status_dir, now)
        online = [t for t in self.state["online"] if t > now - 86400]
        if snap["heartbeat_age"] is not None and snap["heartbeat_age"] < 180:
            online.append(now)
        self.state["online"] = online
        summary = None
        local = dt.datetime.fromtimestamp(now)
        today = local.date().isoformat()
        if local.hour >= self.summary_hour and self.state["last_summary"] != today:
            since = now - 86400
            summary = build_summary(
                snap["levels"], self.state["levels_then"] or snap["levels"],
                online_minutes=len(online),
                restarts=count_log_lines(self.status_dir / "supervisor.log", "restarting:", since),
                stops=count_log_lines(self.status_dir / "skillbot.log", "stopped", since),
                step=snap["status"].get("step"))
            self.state["last_summary"] = today
            self.state["levels_then"] = snap["levels"]
        self.save()
        return summary
