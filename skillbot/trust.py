"""Trust levels per plan step: experimental → trial → trusted.

| level        | runs                                                          |
|--------------|---------------------------------------------------------------|
| experimental | only with `run --supervised` (stops at the first error)       |
| trial        | unattended, in slices of at most 2 hours, reported after each |
| trusted      | normally                                                      |

Promotion: 2 hours supervised without an error → trial; 24 trial hours over at least
3 days, with at most one error per 4 hours and no stops → trusted. A trusted step that
stops the bot twice within 24 hours drops back to trial, and so does any step whose
code or settings change (an experimental one stays experimental).

Stored per account in data/trust.json.
"""
import datetime as dt
import hashlib
import inspect
import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

LEVELS = ("experimental", "trial", "trusted")
SUPERVISED_HOURS = 2
TRIAL_HOURS, TRIAL_DAYS, HOURS_PER_ERROR = 24, 3, 4
TRIAL_SLICE_MINUTES = 120
DEMOTE_STOPS, DEMOTE_WINDOW = 2, 86400


def fingerprint(step, task_cls) -> str:
    """Changes when the step's settings or its task's code change."""
    settings = json.dumps(asdict(step) if is_dataclass(step) else step, sort_keys=True,
                          default=str)
    try:
        code = inspect.getsource(inspect.getmodule(task_cls))
    except (OSError, TypeError):
        code = task_cls.__name__
    return hashlib.sha256((settings + code).encode()).hexdigest()[:16]


def _new(code: str) -> dict:
    return {"level": "experimental", "code": code, "supervised_s": 0.0, "trial_s": 0.0,
            "trial_days": [], "trial_errors": 0, "trial_stops": 0, "stops": []}


class TrustStore:
    def __init__(self, path: Path | None, clock=time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self.data = {}
        if self.path and self.path.exists():
            self.data = json.loads(self.path.read_text())

    def save(self) -> None:
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1))
            tmp.replace(self.path)

    def record(self, name: str, code: str) -> tuple[dict, str | None]:
        """The step's record, reset if its code changed. Returns (record, message)."""
        rec = self.data.get(name)
        message = None
        if rec is None:
            rec = self.data[name] = _new(code)
        elif rec["code"] != code:
            was = rec["level"]
            rec.update(_new(code), level="experimental" if was == "experimental" else "trial")
            if was != "experimental":
                message = f"{name}: code or settings changed, back to trial"
        self.save()
        return rec, message

    def level(self, name: str) -> str:
        return self.data.get(name, {}).get("level", "experimental")

    def set_level(self, name: str, level: str, code: str = "") -> None:
        if level not in LEVELS:
            raise ValueError(f"level must be one of {LEVELS}")
        rec = self.data.setdefault(name, _new(code))
        rec.update(level=level, supervised_s=0.0, trial_s=0.0, trial_days=[], trial_errors=0,
                   trial_stops=0)
        self.save()

    # ---- events ------------------------------------------------------------------------
    def add_time(self, name: str, seconds: float, supervised: bool) -> None:
        rec = self.data[name]
        if supervised:
            rec["supervised_s"] += seconds
        elif rec["level"] == "trial":
            rec["trial_s"] += seconds
            day = dt.date.fromtimestamp(self.clock()).isoformat()
            if day not in rec["trial_days"]:
                rec["trial_days"].append(day)
        self.save()

    def add_error(self, name: str, supervised: bool) -> None:
        rec = self.data[name]
        if supervised:
            rec["supervised_s"] = 0.0       # the 2 clean hours start over
        elif rec["level"] == "trial":
            rec["trial_errors"] += 1
        self.save()

    def add_stop(self, name: str) -> None:
        rec = self.data[name]
        now = self.clock()
        rec["stops"] = [t for t in rec["stops"] if t > now - DEMOTE_WINDOW] + [now]
        if rec["level"] == "trial":
            rec["trial_stops"] += 1
        self.save()

    # ---- promotion and demotion --------------------------------------------------------
    def evaluate(self, name: str) -> str | None:
        rec = self.data[name]
        msg = None
        if rec["level"] == "experimental" and rec["supervised_s"] >= SUPERVISED_HOURS * 3600:
            rec.update(level="trial", trial_s=0.0, trial_days=[], trial_errors=0, trial_stops=0)
            msg = f"{name}: promoted to trial (2 clean supervised hours)"
        elif rec["level"] == "trial":
            hours = rec["trial_s"] / 3600
            if (hours >= TRIAL_HOURS and len(rec["trial_days"]) >= TRIAL_DAYS
                    and rec["trial_errors"] <= hours / HOURS_PER_ERROR
                    and rec["trial_stops"] == 0):
                rec["level"] = "trusted"
                msg = f"{name}: promoted to trusted ({hours:.0f} trial hours, " \
                      f"{rec['trial_errors']} recovered errors)"
        elif rec["level"] == "trusted":
            recent = [t for t in rec["stops"] if t > self.clock() - DEMOTE_WINDOW]
            if len(recent) >= DEMOTE_STOPS:
                rec.update(level="trial", trial_s=0.0, trial_days=[], trial_errors=0,
                           trial_stops=0)
                msg = f"{name}: demoted to trial ({len(recent)} stops in 24h)"
        self.save()
        return msg

    def progress(self, name: str) -> str:
        rec = self.data.get(name)
        if rec is None:
            return "experimental (never run)"
        if rec["level"] == "experimental":
            return f"experimental: {rec['supervised_s'] / 3600:.1f}/{SUPERVISED_HOURS}h supervised"
        if rec["level"] == "trial":
            return (f"trial: {rec['trial_s'] / 3600:.1f}/{TRIAL_HOURS}h over "
                    f"{len(rec['trial_days'])}/{TRIAL_DAYS} days, {rec['trial_errors']} errors, "
                    f"{rec['trial_stops']} stops")
        return "trusted"
