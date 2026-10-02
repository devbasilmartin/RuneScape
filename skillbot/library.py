"""The method library: every training method described once, in library/*.yaml.

    willows_draynor:
      name: "willows (Draynor)"
      skills: [woodcutting]
      levels: [30, 60]                 # use from 30; move on at 60
      requires: {levels: {}, quests: []}
      xp_per_hour: 40000               # rough estimates, for planning only
      profit_per_hour: 30000           # gp; negative = costs money
      reliability: 5                   # 1-5: how well it runs unattended
      location: "draynor willows"      # a destination (navigation)
      step: {task: gather, target: willow_tree, items: [willow_logs], ...}

Combat methods list several skills and a style per skill (`styles`).
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .colors import Registry, resolve_config
from .config import Step

REPO_DIR = Path(__file__).resolve().parent.parent
STYLE_FOR = {"attack": 0, "strength": 1, "defence": 3}


@dataclass
class Method:
    id: str
    name: str
    skills: tuple
    levels: tuple = (1, 99)
    requires_levels: dict = field(default_factory=dict)
    requires_quests: tuple = ()
    xp_per_hour: float = 0
    profit_per_hour: float = 0
    reliability: int = 3
    location: str | None = None
    styles: dict = field(default_factory=dict)
    step: dict = field(default_factory=dict)
    trade: dict | None = None         # {inputs: {item: per hour}, outputs: {item: per hour}}

    @classmethod
    def from_dict(cls, mid: str, d: dict) -> "Method":
        req = d.get("requires") or {}
        skills = tuple(d.get("skills") or [])
        if not skills:
            raise ValueError(f"method {mid}: needs skills")
        return cls(mid, d.get("name", mid), skills, tuple(d.get("levels", (1, 99))),
                   dict(req.get("levels") or {}), tuple(req.get("quests") or ()),
                   float(d.get("xp_per_hour", 0)), float(d.get("profit_per_hour", 0)),
                   int(d.get("reliability", 3)), d.get("location"),
                   dict(d.get("styles") or {}), dict(d.get("step") or {}), d.get("trade"))

    def to_step(self, skill: str, until_level: int, max_minutes: float,
                registry: Registry) -> Step:
        raw = {"name": f"{self.name}" + (f" ({skill})" if len(self.skills) > 1 else ""),
               "skill": skill, "until_level": until_level, "max_minutes": max_minutes,
               **self.step}
        if self.location and "location" not in raw:
            raw["location"] = self.location
        if skill in self.styles:
            raw["style"] = self.styles[skill]
        elif self.step.get("task") == "combat" and skill in STYLE_FOR:
            raw.setdefault("style", STYLE_FOR[skill])
        raw = resolve_config({"plan": [raw]}, registry)["plan"][0]
        return Step.from_dict(raw)


def load_library(folder: Path | None = None) -> dict[str, Method]:
    folder = Path(folder or REPO_DIR / "library")
    methods = {}
    for path in sorted(folder.glob("*.yaml")):
        for mid, spec in (yaml.safe_load(path.read_text()) or {}).items():
            if mid in methods:
                raise ValueError(f"method {mid} is defined twice ({path.name})")
            methods[mid] = Method.from_dict(mid, spec)
    return methods
