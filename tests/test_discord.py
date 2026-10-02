import datetime as dt
import json
import subprocess

from skillbot.discord_core import DiscordCore, count_log_lines
from skillbot.messages import Mailbox
from skillbot.status import build_summary, format_status, snapshot, write_status


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_mailbox_post_and_deliver(tmp_path):
    box = Mailbox(tmp_path, clock=Clock(1000.0))
    a = box.post("one")
    box.clock.t += 1
    box.post("two", image="shot.png")
    pending = box.pending()
    assert [m["text"] for m in pending] == ["one", "two"]      # oldest first
    box.delivered(a)
    assert [m["text"] for m in box.pending()] == ["two"]


def test_question_round_trip(tmp_path):
    box = Mailbox(tmp_path)
    ask_id = box.ask("Which monster?", ["Fire giants", "Skip"], key="slayer-1")
    assert box.ask("Which monster?", ["Fire giants", "Skip"], key="slayer-1") == ask_id
    msg = box.pending()[0]
    assert msg["kind"] == "ask" and msg["options"] == ["Fire giants", "Skip"]
    assert box.answer(ask_id) is None
    assert box.reply(ask_id, "Fire giants")
    assert not box.reply(ask_id, "again")                    # no longer open
    assert box.answer(ask_id) == "Fire giants"
    assert box.answer(ask_id) is None                        # consumed


def fake_run(state="active", code=0):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        out = state if cmd[2] == "is-active" else ""
        return subprocess.CompletedProcess(cmd, code, stdout=out + "\n", stderr="boom")
    run.calls = calls
    return run


def test_commands(tmp_path):
    run = fake_run()
    core = DiscordCore(tmp_path, run=run, clock=Clock(5000.0))
    (tmp_path / "heartbeat.json").write_text(json.dumps({"time": 4990.0}))
    write_status(tmp_path, step="willows", skill="woodcutting", level=45, target=60,
                 stats={"items": 120})
    text = core.command("status")
    assert "active" in text and "running" in text and "willows" in text and "items 120" in text
    assert "paused" not in text
    assert "Paused" in core.command("pause") and (tmp_path / "paused").exists()
    assert "(paused)" in core.command("status")
    core.command("resume")
    assert not (tmp_path / "paused").exists()
    assert core.command("start") == "Supervisor started."
    assert ["systemctl", "--user", "start", "skillbot.service"] in run.calls
    assert "failed" in DiscordCore(tmp_path, run=fake_run(code=1)).command("stop")
    assert "Unknown" in core.command("rm -rf")


def test_answers_by_button_and_reply(tmp_path):
    core = DiscordCore(tmp_path)
    a = core.mailbox.ask("Host?", ["Alice", "Bob"])
    assert core.answer_by_button(a, 1) == "Got it: Bob"
    assert core.mailbox.answer(a) == "Bob"
    assert "already answered" in core.answer_by_button(a, 0)

    b = core.mailbox.ask("Which monster?", ["Skip"])
    core.remember_ask_message(42, b)
    assert core.answer_by_reply(999, "hello") is None          # not a question message
    assert core.answer_by_reply(42, "  kalphites ") == "Got it: kalphites"
    assert core.mailbox.answer(b) == "kalphites"
    # the mapping survives a restart of the service
    core.remember_ask_message(43, core.mailbox.ask("Again?", ["x"]))
    again = DiscordCore(tmp_path)
    assert again.answer_by_reply(43, "y") == "Got it: y"


def test_uptime_and_daily_summary(tmp_path):
    day = dt.datetime(2026, 10, 2, 8, 0).timestamp()
    clock = Clock(day)
    core = DiscordCore(tmp_path, summary_hour=9, clock=clock)
    (tmp_path / "progress.json").write_text(json.dumps({"levels": {"woodcutting": 50}}))
    # online for 30 minutes before 9:00
    for _ in range(30):
        (tmp_path / "heartbeat.json").write_text(json.dumps({"time": clock.t}))
        assert core.tick() is None
        clock.t += 60
    clock.t = day + 3600 + 60                                   # 9:01, bot offline
    (tmp_path / "progress.json").write_text(json.dumps({"levels": {"woodcutting": 52}}))
    summary = core.tick()
    assert "Online: 0h 30m" in summary and "no level-ups" in summary   # first summary: baseline
    clock.t += 60
    assert core.tick() is None                                  # once a day
    clock.t = day + 86400 + 3600 + 60                           # next day 9:01
    (tmp_path / "progress.json").write_text(json.dumps({"levels": {"woodcutting": 55}}))
    summary = core.tick()
    assert "Woodcutting 52 → 55" in summary


def test_summary_marks_99s():
    text = build_summary({"cooking": 99, "magic": 60}, {"cooking": 98, "magic": 60}, 600, 1, 0,
                         "wines")
    assert "99 Cooking" in text and "Online: 10h 0m" in text and "Now: wines" in text


def test_count_log_lines(tmp_path):
    log = tmp_path / "supervisor.log"
    log.write_text("2026-10-01 08:00:00,000 WARNING restarting: old\n"
                   "2026-10-02 08:00:00,000 WARNING restarting: the bot crashed\n"
                   "2026-10-02 08:05:00,000 INFO bot started\n"
                   "garbage line restarting:\n")
    since = dt.datetime(2026, 10, 2, 0, 0).timestamp()
    assert count_log_lines(log, "restarting:", since) == 1
    assert count_log_lines(tmp_path / "missing.log", "x", 0) == 0


def test_status_when_nothing_ran(tmp_path):
    text = format_status(snapshot(tmp_path), "inactive")
    assert "inactive" in text and "never" in text


def test_notify_goes_to_mailbox_when_discord_configured(tmp_path, monkeypatch):
    from skillbot import notify as notify_mod
    notify_mod.setup(tmp_path)
    monkeypatch.delenv("SKILLBOT_DISCORD_TOKEN", raising=False)
    notify_mod.notify("not configured")
    assert Mailbox(tmp_path).pending() == []
    monkeypatch.setenv("SKILLBOT_DISCORD_TOKEN", "x")
    notify_mod.notify("bot stopped")
    assert [m["text"] for m in Mailbox(tmp_path).pending()] == ["bot stopped"]
