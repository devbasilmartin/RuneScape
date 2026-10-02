"""What the bot is doing right now (data/status.json), and a snapshot of everything the
Discord service reports: paused or not, heartbeat age, current step, levels."""
import time
from pathlib import Path

from .heartbeat import last_beat
from .messages import _read, _write


def write_status(data_dir: Path, **fields) -> None:
    _write(Path(data_dir) / "status.json", {**fields, "updated": time.time()})


def snapshot(data_dir: Path, now: float | None = None) -> dict:
    data_dir = Path(data_dir)
    now = time.time() if now is None else now
    beat = last_beat(data_dir / "heartbeat.json")
    progress = _read(data_dir / "progress.json") or {}
    return {
        "paused": (data_dir / "paused").exists(),
        "heartbeat_age": None if beat is None else now - beat,
        "status": _read(data_dir / "status.json") or {},
        "levels": progress.get("levels", {}),
    }


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    if seconds < 90:
        return f"{int(seconds)}s ago"
    if seconds < 5400:
        return f"{int(seconds // 60)}m ago"
    return f"{seconds / 3600:.1f}h ago"


def format_status(snap: dict, supervisor_state: str = "unknown") -> str:
    st = snap["status"]
    alive = snap["heartbeat_age"] is not None and snap["heartbeat_age"] < 180
    lines = [
        f"**Supervisor:** {supervisor_state}" + (" (paused)" if snap["paused"] else ""),
        f"**Bot:** {'running' if alive else 'not running'} "
        f"(last heartbeat {format_age(snap['heartbeat_age'])})",
    ]
    if st.get("step"):
        lines.append(f"**Step:** {st['step']}: {st.get('skill', '?')} "
                     f"{st.get('level', '?')} → {st.get('target', '?')}")
        if st.get("stats"):
            stats = ", ".join(f"{k} {v}" for k, v in st["stats"].items())
            lines.append(f"**This step:** {stats}")
    return "\n".join(lines)


def format_levels(levels: dict) -> str:
    if not levels:
        return "No levels read yet."
    total = sum(levels.values())
    rows = [f"{skill.title()}: {level}" for skill, level in sorted(levels.items())]
    return "\n".join(rows) + f"\n**Total (known skills):** {total}"


def build_summary(levels_now: dict, levels_then: dict, online_minutes: int,
                  restarts: int, stops: int, step: str | None) -> str:
    gained = {s: lvl - levels_then.get(s, lvl) for s, lvl in levels_now.items()}
    gains = [f"{s.title()} {levels_then.get(s, levels_now[s])} → {levels_now[s]}"
             for s, g in sorted(gained.items(), key=lambda kv: -kv[1]) if g > 0]
    nines = [s.title() for s, lvl in levels_now.items()
             if lvl >= 99 and levels_then.get(s, lvl) < 99]
    lines = ["**Daily summary**",
             f"Online: {online_minutes // 60}h {online_minutes % 60}m of the last 24h",
             "Levels: " + (", ".join(gains) if gains else "no level-ups"),
             f"Restarts: {restarts} · stops: {stops}"]
    if step:
        lines.append(f"Now: {step}")
    if nines:
        lines.insert(1, "🎉 99 " + ", ".join(nines))
    return "\n".join(lines)
