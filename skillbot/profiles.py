"""Account profiles: one folder per account, one account running at a time.

    profiles/<name>/config.yaml     that account's config and plan
    profiles/<name>/data/           its calibration, learned digits, levels, logs
    profiles/active                 the name of the account the services run
    ~/.config/skillbot/profiles/<name>.env   its login (and anything else per account)

Without any profiles, everything works as before (config.yaml and data/ at the top).
The Discord mailbox is shared by all profiles and lives in the top-level data/discord/.
"""
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


@dataclass
class Selection:
    name: str | None          # None: no profiles in use
    config_path: Path
    data_dir: Path | None     # None: use whatever the config says


class Profiles:
    def __init__(self, root: Path = REPO_DIR, env_dir: Path | None = None):
        self.root = Path(root)
        self.dir = self.root / "profiles"
        self.env_dir = env_dir or Path.home() / ".config" / "skillbot" / "profiles"

    @property
    def shared_data(self) -> Path:
        return self.root / "data"

    def names(self) -> list[str]:
        if not self.dir.exists():
            return []
        return sorted(p.name for p in self.dir.iterdir() if (p / "config.yaml").exists())

    def active(self) -> str | None:
        path = self.dir / "active"
        name = path.read_text().strip() if path.exists() else ""
        return name if name in self.names() else None

    def use(self, name: str) -> None:
        if name not in self.names():
            raise ValueError(f"no profile {name!r} (have: {', '.join(self.names()) or 'none'})")
        (self.dir / "active").write_text(name + "\n")

    def create(self, name: str, template: Path | None = None) -> Path:
        if not NAME.match(name):
            raise ValueError("profile names are letters, digits, - and _ (max 32)")
        folder = self.dir / name
        if (folder / "config.yaml").exists():
            raise ValueError(f"profile {name!r} already exists")
        (folder / "data").mkdir(parents=True, exist_ok=True)
        src = template or self.root / "config.example.yaml"
        shutil.copy(src, folder / "config.yaml")
        return folder

    def select(self, explicit: str | None, config_arg: str) -> Selection:
        """Which config and data folder to use: --profile, else the active profile,
        else the top-level config.yaml (no profiles)."""
        name = explicit or self.active()
        if explicit and explicit not in self.names():
            raise ValueError(f"no profile {explicit!r}; create it with "
                             f"`python -m skillbot profile create {explicit}`")
        if name is None:
            return Selection(None, Path(config_arg), None)
        folder = self.dir / name
        return Selection(name, folder / "config.yaml", folder / "data")

    def load_env(self, name: str, environ=os.environ) -> list[str]:
        """Apply the profile's env file (its login etc.) over the environment.
        Returns the keys set."""
        path = self.env_dir / f"{name}.env"
        if not path.exists():
            return []
        keys = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            environ[key] = value
            keys.append(key)
        return keys
