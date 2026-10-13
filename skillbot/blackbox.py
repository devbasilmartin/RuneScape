"""The black box: the bot keeps its last minute or so of screens in memory, and when it
stops on an error it writes them out, so nobody has to have been recording.

Every screen grab is offered to it (at most one kept every EVERY seconds, the newest KEEP).
On an error, data/incidents/<time>/ gets:
- frames.png: SHEET frames spread over the last stretch, the last one being the moment of
  the error, each with the time, the mouse (a cross) and what the bot was doing;
- last.png: the final screen, full size;
- log.txt: the end of the log, and why it stopped.
Send to PC includes the newest one. Only the newest KEEP_INCIDENTS are kept.
"""
import collections
import logging
import shutil
import time
from pathlib import Path

log = logging.getLogger("skillbot")

EVERY = 2.0
KEEP = 40                 # 80 seconds
SHEET = 9
KEEP_INCIDENTS = 20
LOG_LINES = 120


class BlackBox:
    def __init__(self, folder: Path, log_file: Path | None = None, mouse=None,
                 clock=time.time):
        self.folder, self.log_file, self.clock = Path(folder), log_file, clock
        self.mouse = mouse or (lambda: None)
        self.shots = collections.deque(maxlen=KEEP)
        self.doing = ""           # the step running now, written under each frame
        self.saved = None         # (time, folder) of the last incident

    def offer(self, img) -> None:
        now = self.clock()
        if self.shots and now - self.shots[-1][0] < EVERY:
            return
        self.shots.append((now, img.copy(), self.mouse(), self.doing))

    def save(self, reason: str, img=None) -> Path | None:
        """Write the incident; returns its folder (None if nothing was seen yet)."""
        if img is not None:
            self.shots.append((self.clock(), img.copy(), self.mouse(), self.doing))
        if not self.shots:
            return None
        import cv2
        from .recorder import annotate, sheet
        from .share import tail
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(self.clock()))
        out = self.folder / stamp
        out.mkdir(parents=True, exist_ok=True)
        shots = list(self.shots)
        n = min(SHEET, len(shots))
        picks = sorted({round(i * (len(shots) - 1) / max(1, n - 1)) for i in range(n)})
        frames = [(shots[i][0], annotate(shots[i][1], shots[i][0], shots[i][2], shots[i][3]))
                  for i in picks]
        cv2.imwrite(str(out / "frames.png"), sheet(frames))
        cv2.imwrite(str(out / "last.png"), shots[-1][1][..., ::-1])
        text = f"stopped: {reason}\n\n"
        if self.log_file is not None:
            text += tail(Path(self.log_file), LOG_LINES)
        (out / "log.txt").write_text(text)
        for old in sorted(p for p in self.folder.iterdir() if p.is_dir())[:-KEEP_INCIDENTS]:
            shutil.rmtree(old, ignore_errors=True)
        self.saved = (self.clock(), out)
        log.info("saved what happened before that: %s (Send to PC includes it)", out)
        return out

    def fresh(self, seconds: float = 60) -> Path | None:
        """The incident saved in the last ``seconds`` (the one that stopped the run)."""
        if self.saved and self.clock() - self.saved[0] <= seconds:
            return self.saved[1]
        return None


def newest(folder: Path) -> Path | None:
    found = sorted(p for p in Path(folder).glob("*") if (p / "frames.png").exists())
    return found[-1] if found else None
