"""Mouse-style A/B testing (docs/mouse.md): which way of moving and aiming lands clicks
on odd-shaped highlights?

With `mouse: {enabled: true}` in config.yaml, clicks on highlights go through the
humanized_input library's Bridge: it picks a style for each click (round-robin or random)
from the styles file, plans the path to a point inside the highlight's outline, and the
bot plays the events. When the step's own check says whether the click worked (an item
gained, a fight started, an obstacle crossed, loot picked up), the outcome is logged per
style with the step's name. `python -m skillbot mouse-summary` shows the rates.

Off by default: the original click path stays until you switch this on.

    mouse:
      enabled: false
      styles: mouse_styles.yaml       # relative to config.yaml
      pick: round-robin               # round-robin | random
      log: mouse_outcomes.jsonl       # in the data folder; kept across sessions

Needs the library: pip install "git+https://github.com/devbasilmartin/Humanized-input@ccr-cf7d2098-mwb8ib"
"""
import logging
from dataclasses import dataclass, fields
from pathlib import Path

log = logging.getLogger("skillbot")

INSTALL = ('pip install "git+https://github.com/devbasilmartin/Humanized-input'
           '@ccr-cf7d2098-mwb8ib"')


@dataclass
class MouseConfig:
    enabled: bool = False
    styles: str = "mouse_styles.yaml"
    pick: str = "round-robin"
    log: str = "mouse_outcomes.jsonl"

    @classmethod
    def from_dict(cls, d: dict | None) -> "MouseConfig":
        d = dict(d or {})
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown mouse keys: {sorted(unknown)}")
        cfg = cls(**d)
        if cfg.pick not in ("round-robin", "random"):
            raise ValueError("mouse.pick must be round-robin or random")
        return cfg


def _bridge_module():
    try:
        from humanized_input import bridge
    except ImportError:
        raise SystemExit(f"mouse styles need the humanized_input library: {INSTALL}")
    return bridge


class MouseLab:
    """One Bridge for the run, and the one click waiting for its outcome."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.pending = None         # (click id, note)
        self.activity = None        # the current step's name, for splitting results

    @classmethod
    def load(cls, cfg: MouseConfig, config_dir: Path, data_dir: Path) -> "MouseLab":
        bridge = _bridge_module()
        styles = Path(cfg.styles)
        if not styles.is_absolute():
            styles = Path(config_dir) / styles
        if not styles.exists():
            raise SystemExit(f"mouse styles file {styles} not found (example: "
                             "mouse_styles.example.yaml)")
        return cls(bridge.Bridge(bridge.load_styles(str(styles)),
                                 log_path=str(Path(data_dir) / cfg.log), pick=cfg.pick))

    def plan(self, start, polygon) -> dict:
        """Plan a click on ``polygon`` from ``start`` (canvas coordinates). An earlier
        click whose outcome never came is dropped, not counted."""
        reply = self.bridge.handle({"cmd": "click", "from": [int(start[0]), int(start[1])],
                                    "polygon": [list(p) for p in polygon]})
        if self.pending is not None:
            self.bridge.pending.pop(self.pending[0], None)
        self.pending = (reply["id"], self.activity)
        return reply

    def outcome(self, ok: bool) -> None:
        if self.pending is None:
            return
        click_id, note = self.pending
        self.pending = None
        msg = {"cmd": "result", "id": click_id, "ok": bool(ok)}
        if note:
            msg["note"] = note
        self.bridge.handle(msg)

    def forget(self) -> None:
        """The click was never made (e.g. the aim was over a random event)."""
        if self.pending is not None:
            self.bridge.pending.pop(self.pending[0], None)
            self.pending = None


def summary_rows(log_path: Path) -> list[dict]:
    """Per style, and per style and step: clicks, ok, rate, mean seconds."""
    import json
    summarize = _bridge_module().summarize
    rows = []
    if not Path(log_path).exists():
        return rows
    outcomes = [json.loads(line) for line in Path(log_path).read_text().splitlines()
                if line.strip()]
    rows += [{"step": "(all)", **r} for r in summarize(outcomes)]
    for note in sorted({o.get("note") for o in outcomes if o.get("note")}):
        rows += [{"step": note, **r} for r in summarize([o for o in outcomes
                                                          if o.get("note") == note])]
    return rows


def format_summary(rows: list[dict]) -> str:
    if not rows:
        return "no mouse outcomes logged yet"
    width = max(len(r["style"]) for r in rows)
    lines, step = [], None
    for r in rows:
        if r["step"] != step:
            step = r["step"]
            lines.append(f"\n{step}:")
        lines.append(f"  {r['style']:<{width}}  {r['ok']:>5}/{r['clicks']:<5} {r['rate']:>7.1%}"
                     f"  {r['mean_s']:.2f}s")
    return "\n".join(lines).lstrip("\n")
