import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from skillbot import ui

ASKS = "name = input('  type a number: '); print('got', name)"
SLOW = "import time\ntry:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    print('saved')"


@pytest.fixture
def app(tmp_path, monkeypatch):
    real = ui.actions

    def fake(steps, exports):
        acts = real(steps, exports)
        acts["ask"] = lambda p: [sys.executable, "-u", "-c", ASKS]
        acts["slow"] = lambda p: [sys.executable, "-u", "-c", SLOW]
        return acts

    monkeypatch.setattr(ui, "actions", fake)
    return ui.App(tmp_path, ["normal trees"], cwd=tmp_path)


def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_a_question_shows_up_and_is_answered(app):
    job = app.start("ask", {})
    assert wait_for(lambda: job.state()["lines"] == ["  type a number: "])
    job.send("42")
    assert wait_for(lambda: not job.running)
    assert job.state()["lines"] == ["  type a number: > 42", "got 42"]


def test_output_with_colons_and_dots_stays_on_one_line(app, monkeypatch):
    job = ui.Job(1, "x", [sys.executable, "-c", "print('saved run orb colors: {...}')"], app.cwd)
    assert wait_for(lambda: not job.running) and job.reader.join(5) is None
    assert job.state()["lines"] == ["saved run orb colors: {...}"]


def test_answers_from_a_form_and_one_job_at_a_time(app):
    job = app.start("ask", {"answers": ["7"]})
    with pytest.raises(ValueError, match="still running"):
        app.start("slow", {})
    assert wait_for(lambda: not job.running)
    assert any(line.endswith("got 7") for line in job.state()["lines"])


def test_stop_is_ctrl_c(app):
    job = app.start("slow", {})
    time.sleep(0.3)
    job.stop()
    assert not job.running and "saved" in job.lines


def test_only_whitelisted_actions_and_checked_parameters(app):
    with pytest.raises(ValueError, match="unknown action"):
        app.start("rm -rf", {})
    with pytest.raises(ValueError, match="pick a step"):
        app.start("check_setup", {"step": "; rm -rf /"})
    with pytest.raises(ValueError, match="pick an export"):
        app.start("runelite_profile", {"export": "/etc/passwd"})
    argv = ui.actions(["normal trees"], [])["check_setup"]({"step": "normal trees"})
    assert argv[-2:] == ["check-setup", "normal trees"]


def test_http(app, tmp_path):
    (tmp_path / "debug.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "secret.png").write_bytes(b"no")
    server = ui.ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"SKILLBOT" in urllib.request.urlopen(base + "/").read()
        state = json.loads(urllib.request.urlopen(base + "/api/state").read())
        assert state["steps"] == ["normal trees"] and state["images"][0]["name"] == "debug.png"
        assert urllib.request.urlopen(base + "/img/debug.png").read() == b"\x89PNG fake"
        for bad in ("/img/secret.png", "/img/../../etc/passwd"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + bad)
        req = urllib.request.Request(base + "/api/start", method="POST",
                                     data=json.dumps({"action": "nope"}).encode())
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400
    finally:
        server.shutdown()
