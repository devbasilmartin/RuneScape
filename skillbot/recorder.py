"""Screen recording (docs/recording.md): a video of what the bot does, for the owner to
watch, and frames from it (frames.png) for Claude, who can look at images but not videos.

A recording is a folder data/recordings/<time>/ of one-minute parts (part-0000.mp4, ...)
and info.json. Each frame has the clock, the mouse position and the bot's latest log line
burnt in under the picture; the VM doesn't draw the mouse, so a cross marks it. Frames are
written at a steady rate (a slow grab repeats the last frame), so a frame's time is its
part's start plus index / fps, and frames.png can pick times by the burnt-in clock.
"""
import json
import re
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

FPS = 5
PART_SECONDS = 60
MAX_MINUTES = 60           # a recording stops by itself after this
STRIP = 24                 # the text strip under the picture
SHEET_FRAMES = 9
SHEET_COLUMNS = 3
SHEET_WIDTH = 1800
LAST_SECONDS = 30          # frames.png without times: the end of the recording


def screen_grab(region=None):
    """A grab function for Recorder: the region (x, y, w, h) or the whole screen, RGB. mss
    is made on the first call, in the recording thread (it can't be shared between
    threads)."""
    sct = []

    def grab():
        if not sct:
            import mss
            sct.append(mss.mss())
        mon = sct[0].monitors[1] if len(sct[0].monitors) > 1 else sct[0].monitors[0]
        box = mon if region is None else {"left": region[0], "top": region[1],
                                          "width": region[2], "height": region[3]}
        return np.asarray(sct[0].grab(box))[..., 2::-1].copy()
    return grab


def game_region(data_dir: Path):
    """The game canvas on screen, from calibration (None before calibrating)."""
    from .layout import CANVAS_H, CANVAS_W
    try:
        x, y = json.loads((Path(data_dir) / "origin.json").read_text())["origin"]
    except (OSError, ValueError, KeyError):
        return None
    return (int(x), int(y), CANVAS_W, CANVAS_H)


def latest_line(log: Path) -> str:
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode(errors="replace").strip().splitlines()
        line = lines[-1] if lines else ""
        # the log's own date and time: the clock is already on the frame
        return re.sub(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ (INFO )?", "", line)
    except OSError:
        return ""


def mouse_position():
    try:
        import pyautogui
        return tuple(pyautogui.position())
    except Exception:          # no display
        return None


def annotate(img: np.ndarray, when: float, mouse, line: str) -> np.ndarray:
    """The picture with a cross at the mouse and a strip of text under it (BGR, even size
    for the video codec)."""
    import cv2
    h, w = img.shape[:2]
    out = np.zeros((h + STRIP + (h + STRIP) % 2, w + w % 2, 3), np.uint8)
    out[:h, :w] = img[..., ::-1]
    if mouse and 0 <= mouse[0] < w and 0 <= mouse[1] < h:
        x, y = int(mouse[0]), int(mouse[1])
        for color, thick in (((0, 0, 0), 3), ((255, 255, 255), 1)):
            cv2.line(out, (x - 9, y), (x + 9, y), color, thick)
            cv2.line(out, (x, y - 9), (x, y + 9), color, thick)
    stamp = datetime.fromtimestamp(when).strftime("%H:%M:%S")
    pos = f"{mouse[0]},{mouse[1]}" if mouse else "-"
    text = f"{stamp}  mouse {pos}  {line}"
    cv2.putText(out, text[:w // 7], (4, h + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (255, 255, 255), 1, cv2.LINE_AA)
    return out


class Recorder:
    """Records in a thread until stop() or MAX_MINUTES. keep_minutes keeps only the last
    few minutes (parts older than that are deleted), for leaving it on during a long run."""

    def __init__(self, folder: Path, grab, region=None, mouse=None,
                 log: Path | None = None, fps: int = FPS, keep_minutes: int | None = None,
                 max_minutes: int = MAX_MINUTES, clock=time.time):
        self.folder, self.grab, self.region = Path(folder), grab, region
        self.mouse, self.log, self.fps = mouse or mouse_position, log, fps
        self.keep_minutes, self.max_minutes, self.clock = keep_minutes, max_minutes, clock
        self.parts: list[dict] = []
        self.started = None
        self.error = ""
        self._writer = None
        self._written = 0
        self._next_part = 0
        self._cut = threading.Event()
        self._cut_done = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.started = self.clock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def cut(self) -> None:
        """Finish the current part now, so it can be read (frames while recording)."""
        if self.running:
            self._cut_done.clear()
            self._cut.set()
            self._cut_done.wait(timeout=5)

    def _local(self, mouse):
        if mouse is None or self.region is None:
            return mouse
        return mouse[0] - self.region[0], mouse[1] - self.region[1]

    def _run(self) -> None:
        try:
            frame = None
            while not self._stop.is_set():
                now = self.clock()
                if now - self.started >= self.max_minutes * 60:
                    break
                frame = annotate(self.grab(), now, self._local(self.mouse()),
                                 latest_line(self.log) if self.log else "")
                with self._lock:
                    if (self._writer is None or self._cut.is_set()
                            or now - self.parts[-1]["start"] >= PART_SECONDS):
                        self._new_part(now, frame)
                        if self._cut.is_set():
                            self._cut.clear()
                            self._cut_done.set()
                    due = int((now - self.parts[-1]["start"]) * self.fps) + 1
                    for _ in range(max(1, due - self._written)):
                        self._writer.write(frame)
                        self._written += 1
                self._stop.wait(max(0.0, self.parts[-1]["start"] + self._written / self.fps
                                    - self.clock()))
        except Exception as e:      # shown in the panel; the bot carries on
            self.error = f"{type(e).__name__}: {e}"
        finally:
            with self._lock:
                self._close()

    def _new_part(self, now: float, frame: np.ndarray) -> None:
        import cv2
        self._close()
        name = f"part-{self._next_part:04d}.mp4"
        self._next_part += 1
        h, w = frame.shape[:2]
        self._writer = cv2.VideoWriter(str(self.folder / name),
                                       cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
        self._written = 0
        self.parts.append({"file": name, "start": now})
        if self.keep_minutes:
            while self.parts and now - self.parts[0]["start"] > self.keep_minutes * 60 + PART_SECONDS:
                (self.folder / self.parts.pop(0)["file"]).unlink(missing_ok=True)
        self._save_info()

    def _close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            self.parts[-1]["frames"] = self._written
            self._save_info()

    def _save_info(self) -> None:
        (self.folder / "info.json").write_text(json.dumps(
            {"fps": self.fps, "region": self.region, "parts": self.parts}, indent=1))

    def state(self) -> dict:
        return {"running": self.running, "folder": str(self.folder), "error": self.error,
                "seconds": int(self.clock() - self.started) if self.started else 0,
                "keep_minutes": self.keep_minutes}


def newest(recordings: Path) -> Path | None:
    found = sorted(p for p in Path(recordings).glob("*") if (p / "info.json").exists())
    return found[-1] if found else None


def parse_time(text: str, day: datetime) -> float:
    """HH:MM:SS (or HH:MM) on the recording's day, as a timestamp."""
    parts = [int(p) for p in text.strip().split(":")]
    if len(parts) not in (2, 3) or not 0 <= parts[0] < 24:
        raise ValueError(f"{text!r}: give a time like 20:41:05, as shown under the video")
    h, m, s = (parts + [0])[:3]
    t = day.replace(hour=h, minute=m, second=s, microsecond=0)
    if t < day - timedelta(hours=12):       # the recording went past midnight
        t += timedelta(days=1)
    return t.timestamp()


def frames(folder: Path, start: str = "", end: str = "", count: int = SHEET_FRAMES):
    """count evenly spaced frames between two clock times (default: the last
    LAST_SECONDS), as [(timestamp, BGR image)]."""
    import cv2
    info = json.loads((Path(folder) / "info.json").read_text())
    parts = [p for p in info["parts"] if p.get("frames")]
    if not parts:
        raise ValueError("nothing recorded yet")
    fps = info["fps"]
    first = parts[0]["start"]
    last = parts[-1]["start"] + (parts[-1]["frames"] - 1) / fps
    day = datetime.fromtimestamp(first)
    t1 = parse_time(end, day) if end else last
    t0 = parse_time(start, day) if start else t1 - LAST_SECONDS
    t0, t1 = max(t0, first), min(t1, last)
    if t1 < t0:
        raise ValueError(f"the recording has {day:%H:%M:%S} to "
                         f"{datetime.fromtimestamp(last):%H:%M:%S}")
    times = [t0 + (t1 - t0) * i / max(1, count - 1) for i in range(count)]
    out = []
    for t in times:
        part = [p for p in parts if p["start"] <= t][-1]
        idx = min(part["frames"] - 1, int((t - part["start"]) * fps))
        cap = cv2.VideoCapture(str(Path(folder) / part["file"]))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, img = cap.read()
        cap.release()
        if ok:
            out.append((t, img))
    return out


def sheet(shots, columns: int = SHEET_COLUMNS, width: int = SHEET_WIDTH) -> np.ndarray:
    """Frames side by side in a grid, each labelled with its time (BGR)."""
    import cv2
    h, w = shots[0][1].shape[:2]
    scale = min(1.0, width / (w * columns))
    cw, ch = int(w * scale), int(h * scale)
    rows = -(-len(shots) // columns)
    out = np.full((rows * (ch + 4), columns * (cw + 4), 3), 40, np.uint8)
    for i, (t, img) in enumerate(shots):
        y, x = (i // columns) * (ch + 4), (i % columns) * (cw + 4)
        out[y:y + ch, x:x + cw] = cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)
        label = datetime.fromtimestamp(t).strftime("%H:%M:%S.") + f"{int(t % 1 * 10)}"
        cv2.putText(out, label, (x + 6, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3,
                    cv2.LINE_AA)
        cv2.putText(out, label, (x + 6, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
    return out


def write_sheet(folder: Path, out: Path, start: str = "", end: str = "") -> Path:
    import cv2
    cv2.imwrite(str(out), sheet(frames(folder, start, end)))
    return out


def copy_parts(folder: Path, dest: Path) -> list[str]:
    """The recording's video parts and info.json, into dest/<recording name>/."""
    target = Path(dest) / Path(folder).name
    target.mkdir(parents=True, exist_ok=True)
    names = []
    for p in sorted(Path(folder).iterdir()):
        if p.suffix in (".mp4", ".json"):
            shutil.copyfile(p, target / p.name)
            names.append(f"{target.name}/{p.name}")
    return names
