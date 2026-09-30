"""Configuration loaded from config.yaml (see config.example.yaml)."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .layout import Layout

MODES = ("drop", "bank", "cook_drop", "cook_bank")


@dataclass
class Config:
    mode: str = "bank"
    data_dir: Path = Path("data")
    fishing_color: tuple = (0, 255, 255)
    bank_color: tuple = (255, 0, 255)
    cook_color: tuple = (255, 255, 0)
    color_tolerance: int = 25
    # Inventory Tags colors, item name -> RGB. Every fish you catch or cook must be tagged.
    items: dict = field(default_factory=lambda: {
        "raw_shrimps": (0, 255, 0),
        "raw_anchovies": (0, 128, 255),
        "shrimps": (255, 128, 0),
        "anchovies": (160, 0, 255),
        "burnt_fish": (255, 0, 0),
    })
    raw_items: tuple = ("raw_shrimps", "raw_anchovies")
    tools: int = 1                    # untagged slots you always carry (net, tinderbox...)
    idle_timeout: float = 25.0        # seconds without a new fish before re-clicking a spot
    spot_adjacent_px: int = 90        # spot must be this close to the player to count as "still fishing"
    cook_idle_timeout: float = 6.0
    walk_timeout: float = 12.0
    bank_open_wait: float = 4.0
    max_failed_clicks: int = 4        # spot clicks in a row with no catch before giving up
    max_runtime_minutes: float = 60.0
    # name -> Ground Marker tile colors, clicked in order when the target isn't on screen
    routes: dict = field(default_factory=dict)
    layout: Layout = field(default_factory=Layout)

    @classmethod
    def load(cls, path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        cfg = cls()
        for key, value in raw.items():
            if key == "layout":
                cfg.layout = Layout.from_dict(value)
            elif not hasattr(cfg, key):
                raise ValueError(f"unknown config key: {key}")
            elif key == "data_dir":
                cfg.data_dir = Path(value)
            elif key == "items":
                cfg.items = {name: tuple(rgb) for name, rgb in value.items()}
            elif key == "routes":
                cfg.routes = {name: [tuple(c) for c in colors] for name, colors in value.items()}
            elif isinstance(getattr(cfg, key), tuple):
                setattr(cfg, key, tuple(value))
            else:
                setattr(cfg, key, value)
        missing = [n for n in cfg.raw_items if n not in cfg.items]
        if missing:
            raise ValueError(f"raw_items {missing} have no color in items")
        if cfg.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {cfg.mode!r}")
        return cfg
