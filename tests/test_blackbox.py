import numpy as np

from skillbot.blackbox import EVERY, KEEP, BlackBox, newest
from skillbot.share import send


def frame(v):
    return np.full((503, 765, 3), v, np.uint8)


def test_keeps_one_screen_every_few_seconds_and_only_the_last_ones(tmp_path):
    t = [0.0]
    box = BlackBox(tmp_path, clock=lambda: t[0])
    for i in range(KEEP * 4):
        box.offer(frame(i % 255))
        t[0] += EVERY / 2
    assert len(box.shots) == KEEP
    assert box.shots[-1][0] - box.shots[0][0] == (KEEP - 1) * EVERY


def test_an_error_writes_frames_last_screen_and_log(tmp_path):
    log = tmp_path / "skillbot.log"
    log.write_text("line one\nclicked the cow\n")
    t = [1_700_000_000.0]
    box = BlackBox(tmp_path / "incidents", log, mouse=lambda: (10, 20), clock=lambda: t[0])
    assert box.save("nothing yet") is None
    for i in range(30):
        box.offer(frame(i))
        t[0] += EVERY
    box.doing = "cows"
    out = box.save("cows: no cow in sight")
    assert {p.name for p in out.iterdir()} == {"frames.png", "last.png", "log.txt"}
    assert "no cow in sight" in (out / "log.txt").read_text()
    assert "clicked the cow" in (out / "log.txt").read_text()
    assert newest(tmp_path / "incidents") == out
    assert box.fresh() == out
    t[0] += 120
    assert box.fresh() is None


def test_send_to_pc_includes_the_newest_error(tmp_path):
    box = BlackBox(tmp_path / "data" / "incidents", clock=lambda: 1_700_000_000.0)
    box.save("oops", frame(5))
    folder, files = send(tmp_path, tmp_path / "data", dest=tmp_path / "share",
                         screenshot=lambda: None)
    assert "error-frames.png" in files and (folder / "error-log.txt").exists()
