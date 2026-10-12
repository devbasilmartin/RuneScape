import json
import time
from datetime import datetime

import numpy as np
import pytest

from skillbot import recorder, ui
from skillbot.recorder import Recorder, annotate, frames, parse_time, sheet


def ramp(clock=time.time):
    """A grey picture that gets brighter with time, to tell frames apart."""
    t0 = clock()
    return lambda: np.full((503, 765, 3), min(250, int((clock() - t0) * 100)), np.uint8)


def record(folder, seconds, **kw):
    rec = Recorder(folder, ramp(), mouse=lambda: (100, 50), fps=10, **kw)
    rec.start()
    time.sleep(seconds)
    rec.stop()
    return rec


def test_annotate_marks_the_mouse_and_adds_a_strip():
    img = np.zeros((503, 765, 3), np.uint8)
    out = annotate(img, 0, (100, 50), "chopping oak")
    assert out.shape[0] % 2 == 0 and out.shape[1] % 2 == 0
    assert out.shape[0] >= 503 + recorder.STRIP
    assert out[50, 100].min() == 255 and out[50, 300].max() == 0
    assert out[503:].max() > 0                       # the text strip has text


def test_records_parts_at_a_steady_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "PART_SECONDS", 0.5)
    rec = record(tmp_path / "rec", 1.6)
    assert not rec.running and not rec.error
    info = json.loads((tmp_path / "rec" / "info.json").read_text())
    assert info["fps"] == 10 and len(info["parts"]) >= 3
    total = sum(p["frames"] for p in info["parts"])
    assert 12 <= total <= 18
    for p in info["parts"]:
        assert (tmp_path / "rec" / p["file"]).stat().st_size > 0


def test_keeps_only_the_last_minutes(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "PART_SECONDS", 0.2)
    record(tmp_path / "rec", 1.5, keep_minutes=0.005)          # 0.3 s
    info = json.loads((tmp_path / "rec" / "info.json").read_text())
    assert info["parts"][0]["file"] != "part-0000.mp4"
    assert len(list((tmp_path / "rec").glob("*.mp4"))) == len(info["parts"]) <= 3


def test_frames_span_the_end_of_the_recording(tmp_path):
    record(tmp_path / "rec", 1.5)
    shots = frames(tmp_path / "rec")
    assert len(shots) == recorder.SHEET_FRAMES
    times = [t for t, _ in shots]
    assert times == sorted(times)
    first, last = shots[0][1][250, 380].mean(), shots[-1][1][250, 380].mean()
    assert first < 30 and last > 100                  # the start and the end
    grid = sheet(shots)
    assert grid.shape[1] <= recorder.SHEET_WIDTH + 12 and grid.shape[0] > 3 * 300


def test_frames_while_recording(tmp_path):
    rec = Recorder(tmp_path / "rec", ramp(), mouse=lambda: None, fps=10)
    rec.start()
    try:
        time.sleep(0.8)
        rec.cut()
        assert len(frames(tmp_path / "rec")) == recorder.SHEET_FRAMES
    finally:
        rec.stop()


def test_times_outside_the_recording(tmp_path):
    record(tmp_path / "rec", 0.5)
    later = f"{(datetime.now().hour + 6) % 24:02d}:00"
    with pytest.raises(ValueError, match="the recording has"):
        frames(tmp_path / "rec", later, later)


def test_parse_time():
    day = datetime(2026, 10, 12, 20, 30)
    assert datetime.fromtimestamp(parse_time("20:41:05", day)) == datetime(2026, 10, 12, 20, 41, 5)
    assert datetime.fromtimestamp(parse_time("00:10", datetime(2026, 10, 12, 23, 50))).day == 13
    for bad in ("soon", "25:00", "1"):
        with pytest.raises(ValueError):
            parse_time(bad, day)


def test_panel_records_and_sends(tmp_path, monkeypatch):
    app = ui.App(tmp_path, [], cwd=tmp_path, library={}, schedules_dir=tmp_path / "s")
    with pytest.raises(ValueError, match="Calibrate"):
        app.record({})
    with pytest.raises(ValueError, match="nothing recorded"):
        app.share_recording({})
    (tmp_path / "origin.json").write_text(json.dumps({"origin": [882, 198]}))
    monkeypatch.setattr(recorder, "screen_grab", lambda region: ramp())
    monkeypatch.setattr(recorder, "mouse_position", lambda: (900, 220))
    share = tmp_path / "sf_pc"
    share.mkdir()
    monkeypatch.setattr("skillbot.share.find_share", lambda: share)
    monkeypatch.setattr("skillbot.share.screen_png", lambda: None)
    assert app.record({}) == "recording the game"
    try:
        with pytest.raises(ValueError, match="already"):
            app.record({})
        time.sleep(0.8)
        assert app.state()["recording"]["running"]
        msg = app.share_recording({})
    finally:
        app.stop_recording()
    assert "frames.png" in msg and (tmp_path / "frames.png").exists()
    sent = next((share / "skillbot").iterdir())
    assert (sent / "frames.png").exists()
    assert list(sent.glob("*/part-0000.mp4")) and list(sent.glob("*/info.json"))
    assert app.stop_recording() == "not recording"


def test_latest_log_line_without_its_date(tmp_path):
    log = tmp_path / "skillbot.log"
    assert recorder.latest_line(log) == ""
    log.write_text("old\n2026-10-12 20:41:05,123 INFO combat: attacking cow\n")
    assert recorder.latest_line(log) == "combat: attacking cow"
