import pytest

from skillbot.profiles import Profiles


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "config.example.yaml").write_text("color_tolerance: 25\n")
    return Profiles(tmp_path, env_dir=tmp_path / "env")


def test_no_profiles_means_top_level_config(repo):
    sel = repo.select(None, "config.yaml")
    assert sel.name is None and str(sel.config_path) == "config.yaml" and sel.data_dir is None


def test_create_use_and_select(repo):
    repo.create("main")
    repo.create("alt_1")
    assert repo.names() == ["alt_1", "main"]
    assert repo.active() is None
    repo.use("main")
    sel = repo.select(None, "config.yaml")
    assert sel.name == "main" and sel.config_path == repo.dir / "main" / "config.yaml"
    assert sel.data_dir == repo.dir / "main" / "data" and sel.data_dir.is_dir()
    assert repo.select("alt_1", "config.yaml").name == "alt_1"     # --profile wins


def test_bad_names_and_missing_profiles(repo):
    with pytest.raises(ValueError):
        repo.create("../escape")
    repo.create("main")
    with pytest.raises(ValueError):
        repo.create("main")
    with pytest.raises(ValueError):
        repo.use("nope")
    with pytest.raises(ValueError):
        repo.select("nope", "config.yaml")


def test_active_profile_that_was_deleted_is_ignored(repo):
    repo.create("main")
    repo.use("main")
    (repo.dir / "main" / "config.yaml").unlink()
    assert repo.active() is None


def test_env_file_overrides_environment(repo):
    repo.env_dir.mkdir()
    (repo.env_dir / "main.env").write_text(
        '# login\nSKILLBOT_USERNAME="alt account"\nexport SKILLBOT_PASSWORD=\'p=ss\'\n\nBROKEN\n')
    env = {"SKILLBOT_USERNAME": "main account"}
    assert repo.load_env("main", env) == ["SKILLBOT_USERNAME", "SKILLBOT_PASSWORD"]
    assert env == {"SKILLBOT_USERNAME": "alt account", "SKILLBOT_PASSWORD": "p=ss"}
    assert repo.load_env("other", env) == []


def test_discord_follows_the_active_profile(repo, tmp_path):
    import json

    from skillbot.discord_core import DiscordCore
    repo.create("main")
    repo.create("alt")
    repo.use("main")
    (repo.dir / "alt" / "data" / "progress.json").write_text(json.dumps({"levels": {"magic": 70}}))
    calls = []

    def run(cmd, **kw):
        import subprocess
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="active\n", stderr="")
    core = DiscordCore(repo.shared_data, run=run, profiles=repo)
    assert "No levels" in core.command("levels")
    assert "**→ main**" in core.command("profile")
    assert "Switching to **alt**" in core.switch("alt")        # a clean handover request
    state = json.loads((repo.shared_data / "rotation.json").read_text())
    assert state["request"]["profile"] == "alt"
    assert not any("restart" in c for c in calls)
    repo.use("alt")                                             # what the supervisor does
    assert "Magic: 70" in core.command("levels")
    core.command("pause")
    assert (repo.dir / "alt" / "data" / "paused").exists()
    assert "no profile" in core.switch("ghost")
