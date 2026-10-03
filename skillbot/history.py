"""Each account's history (data/history.jsonl) and an overview of every account.

One JSON object per line, appended as things happen:

    {"time": ..., "event": "session_start", "levels": {...}}
    {"time": ..., "event": "step", "step": "willows", "skill": "woodcutting",
     "from": 41, "to": 43, "target": 60, "minutes": 118.5, "stats": {...}}
    {"time": ..., "event": "session_end", "reason": "handover", "levels": {...}}

`skillbot accounts` (and Discord /accounts) read it together with the account's levels,
current step and Slayer task; `--json` gives the same for your own scripts.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from .messages import _read

FILE = "history.jsonl"


def log_event(data_dir, event: str, now: float | None = None, **fields) -> None:
    path = Path(data_dir) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"time": time.time() if now is None else now, "event": event, **fields}
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def read_events(data_dir, last: int | None = None) -> list[dict]:
    path = Path(data_dir) / FILE
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue                       # a line cut short by a crash
    return events[-last:] if last else events


def played_seconds(events, since: float = 0.0, now: float | None = None) -> float:
    """Time between session starts and ends (an open session counts up to ``now``)."""
    now = time.time() if now is None else now
    total, start = 0.0, None
    for e in events:
        if e["event"] == "session_start":
            start = e["time"]
        elif e["event"] == "session_end" and start is not None:
            total += max(0.0, e["time"] - max(start, since))
            start = None
    if start is not None:
        total += max(0.0, now - max(start, since))
    return total


def day_start(now: float) -> float:
    d = datetime.fromtimestamp(now)
    return datetime(d.year, d.month, d.day).timestamp()


def account_summary(name: str | None, data_dir, now: float | None = None) -> dict:
    data_dir = Path(data_dir)
    now = time.time() if now is None else now
    events = read_events(data_dir)
    levels = (_read(data_dir / "progress.json") or {}).get("levels", {})
    status = _read(data_dir / "status.json") or {}
    slayer = _read(data_dir / "slayer.json") or {}
    ends = [e for e in events if e["event"] == "session_end"]
    starts = [e for e in events if e["event"] == "session_start"]
    running = bool(starts) and (not ends or starts[-1]["time"] > ends[-1]["time"])
    return {
        "profile": name,
        "total_level": sum(levels.values()),
        "levels": levels,
        "step": status.get("step"),
        "skill": status.get("skill"),
        "level": status.get("level"),
        "target": status.get("target"),
        "slayer": {k: slayer.get(k) for k in ("state", "monster", "left", "done")} if slayer
        else None,
        "running": running,
        "last_played": (now if running else ends[-1]["time"]) if ends or running else None,
        "last_stop": ends[-1].get("reason") if ends else None,
        "hours_today": round(played_seconds(events, day_start(now), now) / 3600, 2),
        "hours_total": round(played_seconds(events, 0.0, now) / 3600, 2),
    }


def format_summary(s: dict, rotation_note: str = "") -> str:
    head = f"**{s['profile'] or 'account'}**" + (" (playing)" if s["running"] else "")
    lines = [head + (f" · {rotation_note}" if rotation_note else ""),
             f"  total level {s['total_level']} · today {s['hours_today']:.1f}h · "
             f"all time {s['hours_total']:.1f}h"]
    if s["step"]:
        lines.append(f"  step: {s['step']} ({s['skill']} {s['level']} → {s['target']})")
    sl = s["slayer"]
    if sl and sl.get("state") == "assigned":
        left = f", {sl['left']} left" if sl.get("left") is not None else ""
        lines.append(f"  slayer: {sl['monster']}{left} ({sl.get('done', 0)} tasks done)")
    elif sl and sl.get("state") in ("asking", "mine"):
        lines.append(f"  slayer: {'waiting for your answer' if sl['state'] == 'asking' else 'yours'}")
    if s["last_stop"] and not s["running"]:
        lines.append(f"  last stop: {s['last_stop']}")
    return "\n".join(lines)


def format_log(events) -> str:
    out = []
    for e in events:
        when = datetime.fromtimestamp(e["time"]).strftime("%m-%d %H:%M")
        if e["event"] == "step":
            out.append(f"{when}  {e['step']}: {e['skill']} {e['from']} → {e['to']} "
                       f"in {e['minutes']:.0f} min")
        elif e["event"] == "session_start":
            out.append(f"{when}  logged in (total {sum(e.get('levels', {}).values())})")
        elif e["event"] == "session_end":
            out.append(f"{when}  stopped: {e.get('reason')}")
        else:
            out.append(f"{when}  {e['event']}")
    return "\n".join(out) or "no history yet"
