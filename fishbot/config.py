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
    tool_slots: tuple = (0,)
    raw_items: tuple = ("raw_shrimps", "raw_anchovies")
    idle_timeout: float = 25.0        # seconds without a new fish before re-clicking a spot
    spot_adjacent_px: int = 90        # spot must be this close to the player to count as "still fishing"
    cook_idle_timeout: float = 6.0
    walk_timeout: float = 12.0
    bank_open_wait: float = 4.0
    max_runtime_minutes: float = 60.0
    routes: dict = field(default_factory=dict)   # name -> list of [dx, dy] minimap offsets (north up)
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
            elif isinstance(getattr(cfg, key), tuple):
                setattr(cfg, key, tuple(value))
            else:
                setattr(cfg, key, value)
        if cfg.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {cfg.mode!r}")
        return cfg
