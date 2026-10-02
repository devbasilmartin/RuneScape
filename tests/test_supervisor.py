import json

import numpy as np
import pytest

from skillbot.heartbeat import Heartbeat, last_beat
from skillbot.supervisor import Supervisor, SupervisorConfig


class Proc:
    def __init__(self, name):
        self.name, self.returncode, self.pid = name, None, 0

    def poll(self):
        return self.returncode


class FakeHost:
    """Time only moves when the supervisor sleeps. ``events`` maps a time to a
    function run once the clock passes it."""

    def __init__(self, data_dir):
        self.t = 0.0
        self.data_dir = data_dir
        self.log = []
        self.clients, self.bots = [], []
        self.window = False
        self.window_after = 10          # seconds after a client start before its window shows
        self.frame = np.zeros((20, 20, 3))
        self.animate = True
        self.events = []
        self.beat_while_running = True

    def now(self):
        return self.t

    def sleep(self, s):
        end = self.t + s
        while self.t < end:
            self.t = min(end, self.t + 5)
            if self.animate:
                self.frame = np.random.default_rng(int(self.t)).integers(0, 255, (20, 20, 3))
            bot = self.bots[-1] if self.bots else None
            if self.beat_while_running and bot and bot.poll() is None:
                (self.data_dir / "heartbeat.json").write_text(json.dumps({"time": self.t}))
            if self.clients and self.t - self.client_started >= self.window_after:
                self.window = self.clients[-1].poll() is None
            for when, fn in list(self.events):
                if self.t >= when:
                    self.events.remove((when, fn))
                    fn()

    def start_client(self):
        p = Proc("client")
        self.clients.append(p)
        self.client_started = self.t
        self.window = False
        self.log.append("start client")
        return p

    def start_bot(self):
        p = Proc("bot")
        self.bots.append(p)
        self.log.append("start bot")
        return p

    def stop(self, proc):
        if proc is not None and proc.returncode is None:
            proc.returncode = -15
            self.log.append(f"stop {proc.name}")

    def release_keys(self):
        self.log.append("release keys")

    def window_exists(self, name):
        return self.window

    def move_window(self, name, x, y):
        self.log.append(f"move window {x},{y}")

    def grab(self):
        return self.frame


CFG = SupervisorConfig(poll_seconds=15, heartbeat_minutes=3, freeze_minutes=5,
                       max_restarts_per_hour=3, client_start_timeout=60,
                       client_settle_seconds=5)


def make(tmp_path, **kw):
    host = FakeHost(tmp_path)
    sent = []
    sup = Supervisor(SupervisorConfig(**{**CFG.__dict__, **kw}), host, tmp_path, notify=sent.append)
    return sup, host, sent


def run_for(sup, host, seconds):
    """Start everything, then run watchdog passes until ``seconds`` have passed."""
    if not host.clients:
        sup.start_everything()
    end = host.t + seconds
    while host.t < end:
        host.sleep(sup.cfg.poll_seconds)
        if not sup.check():
            return False
    return True


def test_starts_client_then_bot_and_moves_window(tmp_path):
    sup, host, _ = make(tmp_path)
    run_for(sup, host, 60)
    assert host.log[:3] == ["start client", "move window 0,0", "start bot"]
    assert len(host.bots) == 1        # healthy: nothing restarted


def test_restarts_crashed_bot_only(tmp_path):
    sup, host, _ = make(tmp_path)
    sup.start_everything()
    host.bots[-1].returncode = 1
    run_for(sup, host, 30)
    assert len(host.bots) == 2 and len(host.clients) == 1
    assert "release keys" in host.log


def test_clean_bot_exit_stops_supervisor(tmp_path):
    sup, host, sent = make(tmp_path)
    sup.start_everything()
    host.bots[-1].returncode = 0
    assert run_for(sup, host, 30) is False
    assert len(host.bots) == 1 and "stopped by itself" in sent[0]


def test_hung_bot_is_restarted(tmp_path):
    sup, host, _ = make(tmp_path)
    host.beat_while_running = False
    run_for(sup, host, 4 * 60)
    assert len(host.bots) == 2


def test_client_exit_restarts_everything(tmp_path):
    sup, host, _ = make(tmp_path)
    sup.start_everything()
    host.clients[-1].returncode = 1
    run_for(sup, host, 60)
    assert len(host.clients) == 2 and len(host.bots) == 2


def test_frozen_screen_restarts_everything(tmp_path):
    sup, host, _ = make(tmp_path)
    sup.start_everything()
    host.animate = False
    run_for(sup, host, 6 * 60)
    assert len(host.clients) == 2


def test_gives_up_after_too_many_restarts(tmp_path):
    sup, host, sent = make(tmp_path)
    host.events = [(t, lambda: setattr(host.bots[-1], "returncode", 1))
                   for t in range(60, 3000, 60)]
    assert sup.run() == 0
    assert any("gave up" in m for m in sent)
    assert len(host.bots) == 1 + 3          # the first start plus three restarts


def test_client_window_never_appears(tmp_path):
    sup, host, sent = make(tmp_path)
    host.window_after = 10 ** 9
    assert sup.run() == 0
    assert any("window never appeared" in m for m in sent)


def test_pause_and_resume(tmp_path):
    sup, host, _ = make(tmp_path)
    sup.start_everything()
    (tmp_path / "paused").write_text("")
    run_for(sup, host, 30)
    assert host.bots[-1].returncode is not None        # stopped for you to play
    host.animate, host.beat_while_running = False, False
    run_for(sup, host, 20 * 60)                        # no watchdog restarts while paused
    assert len(host.bots) == 1 and len(host.clients) == 1
    (tmp_path / "paused").unlink()
    host.animate, host.beat_while_running = True, True
    run_for(sup, host, 30)
    assert len(host.bots) == 2 and host.bots[-1].poll() is None


def test_heartbeat_throttles_and_reads(tmp_path):
    t = [100.0]
    hb = Heartbeat(tmp_path / "hb.json", every=10, clock=lambda: t[0])
    hb.beat()
    t[0] = 105
    hb.beat()
    assert last_beat(tmp_path / "hb.json") == 100
    t[0] = 111
    hb.beat()
    assert last_beat(tmp_path / "hb.json") == 111
    assert last_beat(tmp_path / "missing.json") is None


def test_config_rejects_unknown_keys():
    with pytest.raises(ValueError):
        SupervisorConfig.from_dict({"freez_minutes": 5})
    assert SupervisorConfig.from_dict({"window_position": [10, 20]}).window_position == (10, 20)
