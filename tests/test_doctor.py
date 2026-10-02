import subprocess

from skillbot.doctor import (FAIL, PASS, WARN, check_calibration, check_capture,
                             check_gsetting, check_screen, check_session)


def test_session():
    assert check_session({}).status == FAIL
    assert check_session({"DISPLAY": ":0", "XDG_SESSION_TYPE": "wayland"}).status == FAIL
    assert check_session({"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11"}).status == PASS


def test_screen_size():
    assert check_screen({"width": 1280, "height": 800}).status == PASS
    assert check_screen({"width": 800, "height": 600}).status == FAIL


def test_capture():
    import numpy as np
    assert check_capture(np.zeros((10, 10, 3))).status == FAIL
    assert check_capture(np.arange(300).reshape(10, 10, 3)).status == PASS


def test_gsetting():
    def fake(value, code=0):
        return lambda *a, **k: subprocess.CompletedProcess(a, code, stdout=value, stderr="")
    assert check_gsetting("s", "idle-delay", "0", "x", run=fake("uint32 0\n")).status == PASS
    assert check_gsetting("s", "idle-delay", "0", "x", run=fake("uint32 300\n")).status == FAIL
    assert check_gsetting("s", "k", "0", "x", run=fake("", code=1)).status == WARN


def test_calibration(tmp_path):
    assert check_calibration(tmp_path).status == WARN
    for f in ("origin.json", "fingerprint.json", "run_orb.json", "digits.json"):
        (tmp_path / f).write_text("{}")
    assert check_calibration(tmp_path).status == PASS
