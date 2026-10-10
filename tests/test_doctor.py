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


def test_os(tmp_path):
    from skillbot.doctor import check_os
    f = tmp_path / "os-release"
    f.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
    assert check_os(f).status == PASS
    f.write_text('ID=ubuntu\nVERSION_ID="26.04"\n')
    assert check_os(f).status == FAIL
    assert check_os(tmp_path / "none").status == WARN


def test_packages_tools_and_login():
    from skillbot.doctor import check_login, check_packages, check_tools
    assert check_packages(find=lambda m: object()).status == PASS
    c = check_packages(find=lambda m: None if m == "cv2" else object())
    assert c.status == FAIL and "opencv-python" in c.detail
    c = check_packages(True, find=lambda m: None if m == "humanized_input" else object())
    assert c.status == FAIL and "humanized_input" in c.detail
    assert check_tools(which=lambda t: None).status == FAIL
    c = check_login("alt", {"SKILLBOT_USERNAME": "u", "SKILLBOT_PASSWORD": "secret"})
    assert c.status == PASS and "secret" not in c.detail
    assert check_login("alt", {"SKILLBOT_USERNAME": "u"}).status == WARN


def test_client_and_runelite_profile(tmp_path):
    from skillbot.doctor import check_client, check_runelite_profile
    found = lambda *a, **k: subprocess.CompletedProcess(a, 0)  # noqa: E731
    gone = lambda *a, **k: subprocess.CompletedProcess(a, 1)   # noqa: E731
    assert check_client("RuneLite", run=found).status == PASS
    assert check_client("RuneLite", run=gone).status == WARN
    assert check_runelite_profile(tmp_path).status == WARN
    (tmp_path / "bot-profile.properties").write_text("")
    assert check_runelite_profile(tmp_path).status == PASS
