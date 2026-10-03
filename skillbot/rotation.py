"""Rotating between account profiles (docs/accounts.md).

rotation.yaml, next to profiles/:

    accounts:
      - {profile: main, hours: 3}
      - {profile: alt, hours: 1.5, max_hours_per_day: 6}
      - {profile: pure, hours: 2, goals: goals-combat.yaml}  # a different goals file per turn
    order: in_order          # in_order | least_played_today | lowest_total_level
    gap_minutes: 1           # logged out between two accounts
    handover_minutes: 10     # how long the bot may take to finish its load and log out

The supervisor runs it: when a turn is over it asks the bot to hand over (the bot
finishes the current batch, logs out and exits), then starts the next account.
`skillbot switch NAME [--hours H]` asks for a specific account next, from a shell,
cron or any script; Discord /switch does the same.

State (whose turn, since when, benched accounts, the pending request) is in
data/rotation.json, shared by all profiles.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .history import account_summary, day_start, played_seconds, read_events

ORDERS = ("in_order", "least_played_today", "lowest_total_level")


@dataclass
class Turn:
    profile: str
    hours: float = 2.0
    max_hours_per_day: float = 0       # 0 = no cap
    goals: str | None = None           # goals file for this account's turns


@dataclass
class RotationConfig:
    accounts: list = field(default_factory=list)
    order: str = "in_order"
    gap_minutes: float = 1.0
    handover_minutes: float = 10.0

    @classmethod
    def from_dict(cls, d: dict, known_profiles=None) -> "RotationConfig":
        d = dict(d or {})
        unknown = set(d) - {"accounts", "order", "gap_minutes", "handover_minutes"}
        if unknown:
            raise ValueError(f"rotation.yaml: unknown keys {sorted(unknown)}")
        turns = []
        for a in d.get("accounts") or []:
            extra = set(a) - {"profile", "hours", "max_hours_per_day", "goals"}
            if extra:
                raise ValueError(f"rotation.yaml: unknown account keys {sorted(extra)}")
            t = Turn(**a)
            if known_profiles is not None and t.profile not in known_profiles:
                raise ValueError(f"rotation.yaml: no profile {t.profile!r}")
            if t.hours <= 0:
                raise ValueError(f"rotation.yaml: {t.profile}: hours must be above 0")
            turns.append(t)
        if not turns:
            raise ValueError("rotation.yaml: list at least one account")
        cfg = cls(turns, d.get("order", "in_order"), float(d.get("gap_minutes", 1.0)),
                  float(d.get("handover_minutes", 10.0)))
        if cfg.order not in ORDERS:
            raise ValueError(f"rotation.yaml: order must be one of {ORDERS}")
        return cfg

    @classmethod
    def load(cls, path: Path, known_profiles=None) -> "RotationConfig | None":
        if not Path(path).exists():
            return None
        return cls.from_dict(yaml.safe_load(Path(path).read_text()), known_profiles)

    def turn(self, profile: str) -> Turn | None:
        return next((t for t in self.accounts if t.profile == profile), None)


class Rotation:
    def __init__(self, cfg: RotationConfig | None, profiles, state_path: Path):
        self.cfg = cfg                  # None: no schedule, only `switch` requests
        self.profiles = profiles
        self.path = Path(state_path)

    # ---- state -------------------------------------------------------------------------
    def state(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        data.setdefault("benched", {})
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(self.path)

    def request(self, profile: str, hours: float | None = None) -> None:
        if profile not in self.profiles.names():
            raise ValueError(f"no profile {profile!r} (have: {', '.join(self.profiles.names())})")
        data = self.state()
        data["request"] = {"profile": profile, "hours": hours}
        self.save(data)

    def take_request(self) -> dict | None:
        data = self.state()
        req = data.pop("request", None)
        if req:
            self.save(data)
        return req

    def bench(self, profile: str, reason: str) -> None:
        data = self.state()
        data["benched"][profile] = reason
        self.save(data)

    def unbench(self, profile: str) -> bool:
        data = self.state()
        found = data["benched"].pop(profile, None) is not None
        self.save(data)
        return found

    def started(self, profile: str, now: float, hours: float | None) -> None:
        data = self.state()
        data.update(current=profile, since=now, hours=hours)
        self.save(data)

    # ---- decisions ---------------------------------------------------------------------
    def hours_for(self, profile: str) -> float | None:
        t = self.cfg.turn(profile) if self.cfg else None
        return t.hours if t else None

    def due(self, now: float) -> bool:
        data = self.state()
        hours = data.get("hours")
        if self.cfg is None or not data.get("current") or not hours:
            return False
        return now - data.get("since", now) >= hours * 3600

    def hours_today(self, profile: str, now: float) -> float:
        return played_seconds(read_events(self.profiles.dir / profile / "data"),
                              day_start(now), now) / 3600

    def eligible(self, now: float) -> list[Turn]:
        benched = self.state()["benched"]
        out = []
        for t in self.cfg.accounts if self.cfg else []:
            if t.profile in benched or t.profile not in self.profiles.names():
                continue
            if t.max_hours_per_day and self.hours_today(t.profile, now) >= t.max_hours_per_day:
                continue
            out.append(t)
        return out

    def next(self, now: float, current: str | None) -> Turn | None:
        """Whose turn is next (may be ``current`` again when it's the only one left)."""
        turns = self.eligible(now)
        if not turns:
            return None
        if self.cfg.order == "in_order":
            names = [t.profile for t in self.cfg.accounts]
            start = names.index(current) + 1 if current in names else 0
            ring = names[start:] + names[:start]
            return next(t for p in ring for t in turns if t.profile == p)
        others = [t for t in turns if t.profile != current] or turns
        if self.cfg.order == "least_played_today":
            return min(others, key=lambda t: self.hours_today(t.profile, now))
        return min(others, key=lambda t: account_summary(
            t.profile, self.profiles.dir / t.profile / "data", now)["total_level"])

    def describe(self, now: float) -> dict:
        """Who's on, until when, and what's next: for `accounts` and Discord."""
        data = self.state()
        current = data.get("current")
        until = data["since"] + data["hours"] * 3600 if data.get("hours") else None
        nxt = self.next(now, current) if self.cfg else None
        return {"current": current, "until": until,
                "next": nxt.profile if nxt else None,
                "benched": dict(data["benched"]),
                "request": data.get("request")}


def overview(profiles, rotation: "Rotation | None", now: float) -> dict:
    """Every account's summary plus the rotation state: `accounts --json`."""
    from .history import account_summary
    accounts = [account_summary(n, profiles.dir / n / "data", now) for n in profiles.names()]
    return {"accounts": accounts,
            "rotation": rotation.describe(now) if rotation is not None else None}


def format_overview(data: dict, now: float) -> str:
    from datetime import datetime

    from .history import format_summary
    rot = data["rotation"] or {}
    out = []
    for s in data["accounts"]:
        note = ""
        if s["profile"] == rot.get("current"):
            until = rot.get("until")
            note = "on now" + (f" until {datetime.fromtimestamp(until):%H:%M}" if until else "")
        elif s["profile"] == rot.get("next"):
            note = "next"
        if s["profile"] in rot.get("benched", {}):
            note = f"benched: {rot['benched'][s['profile']]}"
        out.append(format_summary(s, note))
    if rot.get("request"):
        out.append(f"switch requested: {rot['request']['profile']}")
    return "\n".join(out) or "No profiles yet."


def load_rotation(profiles) -> "Rotation | None":
    """The rotation for these profiles (schedule optional), or None without profiles."""
    if not profiles.names():
        return None
    cfg = RotationConfig.load(profiles.root / "rotation.yaml", profiles.names())
    return Rotation(cfg, profiles, profiles.shared_data / "rotation.json")
