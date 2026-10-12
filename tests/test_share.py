import pytest

from skillbot.share import KEEP, send


def test_send_copies_images_log_and_output(tmp_path):
    repo, data, share = tmp_path / "repo", tmp_path / "data", tmp_path / "sf_pc"
    for d in (repo, data, share):
        d.mkdir()
    (repo / "debug.png").write_bytes(b"png")
    (data / "skillbot.log").write_text("".join(f"line {i}\n" for i in range(1000)))
    folder, files = send(repo, data, ["run_activity: finished"], dest=share,
                         screenshot=lambda: b"screen", now=0)
    assert files == ["screen.png", "debug.png", "skillbot-log.txt", "panel-output.txt"]
    assert folder.parent == share / "skillbot"
    log = (folder / "skillbot-log.txt").read_text().splitlines()
    assert log[-1] == "line 999" and len(log) == 300
    assert (folder / "panel-output.txt").read_text() == "run_activity: finished\n"


def test_keeps_only_the_newest_sends(tmp_path):
    for t in range(KEEP + 3):
        send(tmp_path, tmp_path, dest=tmp_path, screenshot=lambda: None, now=t * 60)
    assert len(list((tmp_path / "skillbot").iterdir())) == KEEP


def test_no_share_says_how_to_set_it_up(tmp_path, monkeypatch):
    monkeypatch.setattr("skillbot.share.find_share", lambda: None)
    with pytest.raises(ValueError, match="share.sh"):
        send(tmp_path, tmp_path, screenshot=lambda: None)
