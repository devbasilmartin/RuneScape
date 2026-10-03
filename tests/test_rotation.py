import json

import pytest

from skillbot.history import account_summary, format_log, log_event, played_seconds, read_events
from skillbot.profiles import Profiles
from skillbot.rotation import Rotation, RotationConfig, format_overview, load_rotation, overview
from skillbot.supervisor import Supervisor

from test_supervisor import CFG, FakeHost

DAY = 86400 * 400          # well into the epoch, so "today" is a whole day


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "config.example.yaml").write_text("plan: []\n")
    p = Profiles(tmp_path, env_dir=tmp_path / "env")
    for name in ("main", "alt", "pure"):
        p.create(name)
    p.use("main")
    return p


def write_rotation(repo, **kw):
    cfg = {"accounts": [{"profile": "main", "hours": 2}, {"profile": "alt", "hours": 1},
                        {"profile": "pure", "hours": 1, "goals": "goals-combat.yaml"}],
           "gap_minutes": 1, **kw}
    import yaml
    (repo.root / "rotation.yaml").write_text(yaml.safe_dump(cfg))
    return load_rotation(repo)


class RotHost(FakeHost):
    """Bots hand over politely: once the handover flag appears they finish within a
    minute, log out and exit 0."""

    def __init__(self, repo):
        super().__init__(repo.dir / "main" / "data")
        self.t = DAY
        self.profile, self.goals, self.repo = "main", None, repo
        self.logged_out = []
        self.polite = True

    def sleep(self, s):
        super().sleep(s)
        bot = self.bots[-1] if self.bots else None
        flag = self.data_dir / "handover"
        if self.polite and bot and bot.poll() is None and flag.exists():
            flag.unlink()
            (self.data_dir / "stopped.json").write_text(json.dumps({"kind": "handover"}))
            bot.returncode = 0

    def start_bot(self):
        self.log.append(f"start bot {self.profile} {self.goals}")
        p = super().start_bot()
        log_event(self.data_dir, "session_start", now=self.t, levels={})
        return p

    def logout(self, profile):
        self.logged_out.append(profile)
        log_event(self.repo.dir / profile / "data", "session_end", now=self.t, reason="x")

    def use_profile(self, profiles, name):
        profiles.use(name)
        self.profile, self.data_dir = name, profiles.dir / name / "data"


def make(repo, rotation):
    host = RotHost(repo)
    sent = []
    sup = Supervisor(CFG, host, host.data_dir, notify=sent.append, rotation=rotation)
    return sup, host, sent


def run_for(sup, host, seconds):
    end = host.t + seconds
    while host.t < end:
        host.sleep(sup.cfg.poll_seconds)
        if not sup.check():
            return False
    return True


def test_turns_rotate_in_order_with_clean_handovers(repo):
    rot = write_rotation(repo)
    sup, host, sent = make(repo, rot)
    sup.begin_rotation()
    sup.start_everything()
    assert run_for(sup, host, 2 * 3600 + 120)
    assert repo.active() == "alt" and host.logged_out == ["main"]
    assert "rotation: main → alt for 1h" in sent
    assert run_for(sup, host, 3600 + 120)
    assert repo.active() == "pure"
    assert "start bot pure goals-combat.yaml" in host.log
    assert len(host.clients) == 1                 # never restarted the client


def test_switch_request_and_impolite_bot(repo):
    rot = write_rotation(repo)
    sup, host, sent = make(repo, rot)
    sup.begin_rotation()
    sup.start_everything()
    host.polite = False                           # ignores the flag: stopped after the timeout
    rot.request("pure", hours=0.5)
    run_for(sup, host, 60)
    assert repo.active() == "main"                # still waiting for the handover
    run_for(sup, host, 10 * 60)
    assert repo.active() == "pure" and "stop bot" in host.log
    assert rot.state()["hours"] == 0.5


def test_a_bot_that_stops_by_itself_is_benched(repo):
    rot = write_rotation(repo)
    sup, host, sent = make(repo, rot)
    sup.begin_rotation()
    sup.start_everything()
    (host.data_dir / "stopped.json").write_text(json.dumps(
        {"kind": "stopped", "detail": "plan complete"}))
    host.bots[-1].returncode = 0
    assert run_for(sup, host, 60)
    assert rot.state()["benched"] == {"main": "plan complete"}
    assert repo.active() == "alt" and host.logged_out == ["main"]
    assert "rotation unbench main" in " ".join(sent)


def test_failsafe_still_stops_everything(repo):
    rot = write_rotation(repo)
    sup, host, sent = make(repo, rot)
    sup.begin_rotation()
    sup.start_everything()
    (host.data_dir / "stopped.json").write_text(json.dumps({"kind": "failsafe"}))
    host.bots[-1].returncode = 0
    assert run_for(sup, host, 60) is False


def test_daily_cap_and_nobody_left(repo):
    rot = write_rotation(repo, accounts=[{"profile": "main", "hours": 5,
                                          "max_hours_per_day": 1}])
    sup, host, sent = make(repo, rot)
    sup.begin_rotation()
    sup.start_everything()
    run_for(sup, host, 3600 + 120)
    assert sup.idle and host.logged_out == ["main"]
    assert "nobody's turn" in sent[-1]
    n = len(host.bots)
    run_for(sup, host, 600)
    assert len(host.bots) == n                    # waits, doesn't restart anything


def test_orders(repo):
    now = DAY + 3600
    for name, hours in (("main", 3), ("alt", 1), ("pure", 2)):
        d = repo.dir / name / "data"
        log_event(d, "session_start", now=DAY + 60)
        log_event(d, "session_end", now=DAY + 60 + hours * 600)
    (repo.dir / "pure" / "data" / "progress.json").write_text('{"levels": {"attack": 5}}')
    (repo.dir / "alt" / "data" / "progress.json").write_text('{"levels": {"attack": 50}}')
    (repo.dir / "main" / "data" / "progress.json").write_text('{"levels": {"attack": 40}}')
    rot = write_rotation(repo, order="least_played_today")
    assert rot.next(now, "main").profile == "alt"
    rot = write_rotation(repo, order="lowest_total_level")
    assert rot.next(now, "pure").profile == "main"
    rot = write_rotation(repo, order="in_order")
    assert rot.next(now, "pure").profile == "main"
    rot.bench("main", "test")
    assert rot.next(now, "pure").profile == "alt"


def test_config_errors(repo):
    with pytest.raises(ValueError, match="no profile"):
        RotationConfig.from_dict({"accounts": [{"profile": "ghost"}]}, repo.names())
    with pytest.raises(ValueError, match="order"):
        RotationConfig.from_dict({"accounts": [{"profile": "main"}], "order": "random"})
    with pytest.raises(ValueError, match="unknown account keys"):
        RotationConfig.from_dict({"accounts": [{"profile": "main", "hour": 2}]})
    assert Rotation(None, repo, repo.shared_data / "r.json").due(DAY) is False


def test_history_and_overview(repo):
    d = repo.dir / "main" / "data"
    log_event(d, "session_start", now=DAY, levels={"attack": 40})
    log_event(d, "step", now=DAY + 3600, step="cows", skill="attack", **{"from": 40},
              to=42, target=60, minutes=60, stats={})
    (d / "progress.json").write_text('{"levels": {"attack": 42, "slayer": 10}}')
    (d / "status.json").write_text('{"step": "slayer", "skill": "slayer", "level": 10, '
                                   '"target": 99}')
    (d / "slayer.json").write_text('{"state": "assigned", "monster": "cows", "left": 12, '
                                   '"done": 3}')
    s = account_summary("main", d, now=DAY + 7200)
    assert s["running"] and s["total_level"] == 52 and s["hours_total"] == 2.0
    assert s["slayer"]["monster"] == "cows"
    assert "cows: attack 40 → 42" in format_log(read_events(d))
    rot = write_rotation(repo)
    rot.started("main", DAY, 2)
    text = format_overview(overview(repo, rot, DAY + 7200), DAY + 7200)
    assert "**main** (playing) · on now until" in text
    assert "slayer: cows, 12 left (3 tasks done)" in text
    assert "**alt** · next" in text
    assert played_seconds([{"time": 0, "event": "session_start"}], 0, 50) == 50
