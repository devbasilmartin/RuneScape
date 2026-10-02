"""The bot's "I'm alive" signal for the watchdog: a small JSON file with a timestamp,
rewritten every few seconds while the bot looks at the screen or waits."""
import json
import os
import time
from pathlib import Path


class Heartbeat:
    def __init__(self, path: Path, every: float = 10.0, clock=time.time):
        self.path = Path(path)
        self.every = every
        self.clock = clock
        self.last = float("-inf")

    def beat(self) -> None:
        now = self.clock()
        if now - self.last < self.every:
            return
        self.last = now
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"time": now, "pid": os.getpid()}))
        tmp.replace(self.path)       # atomic, so the watchdog never reads half a file


def last_beat(path: Path) -> float | None:
    try:
        return float(json.loads(Path(path).read_text())["time"])
    except (OSError, ValueError, KeyError):
        return None
