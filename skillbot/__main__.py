"""Command line: python -m skillbot {calibrate,learn-digits,levels,debug,run}."""
import argparse
import json
import logging
import logging.handlers
from pathlib import Path

import cv2

from . import vision
from .config import Config
from .game import Game, StopBot
from .inventory import SLOTS, Inventory
from .planner import Levels, Planner
from .run import RunManager, orb_sample
from .screen import Screen
from .session import Session, sample
from .skills import SKILLS, SkillReader


def cmd_calibrate(cfg: Config, args) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    if args.origin:
        origin = tuple(args.origin)
    else:
        import pyautogui
        input("Put RuneLite in FIXED mode and log in. Hover the mouse over the top-left pixel "
              "of the game canvas (not the window title bar) and press Enter...")
        origin = tuple(pyautogui.position())
    (cfg.data_dir / "origin.json").write_text(json.dumps({"origin": origin}))
    img = Screen(origin).grab()
    fp = sample(img, cfg.layout.fingerprint_points)
    (cfg.data_dir / "fingerprint.json").write_text(json.dumps(fp))
    print(f"canvas origin = {origin}; logged-in fingerprint saved. "
          "Run `python -m skillbot debug` to check it.")


def cmd_calibrate_run(cfg: Config, args) -> None:
    screen = Screen.load(cfg.data_dir)
    samples = {}
    for state in ("on", "off"):
        input(f"Turn run {state.upper()} (click the run orb), then press Enter...")
        samples[state] = orb_sample(screen.grab(), cfg.layout.run_orb)
    gap = max(abs(a - b) for a, b in zip(samples["on"], samples["off"]))
    if gap < 30:
        raise SystemExit(f"on/off look almost the same ({samples}); check layout.run_orb "
                         "with `python -m skillbot debug`")
    (cfg.data_dir / "run_orb.json").write_text(json.dumps(samples))
    print(f"saved run orb colors: {samples}")


def cmd_learn_digits(cfg: Config, args) -> None:
    img = Screen.load(cfg.data_dir).grab()
    reader = SkillReader.load(cfg.layout, cfg.data_dir)
    print("With the skills tab open, type the level shown for each skill "
          "(Enter to skip; skip unreadable ones).")
    for skill in SKILLS:
        text = input(f"  {skill}: ").strip()
        if text.isdigit() and not reader.learn(img, skill, int(text)):
            print(f"    could not split {skill} into {len(text)} digits; check skill_level_box")
    reader.save()
    print(f"known digits: {reader.known_digits() or 'none'}. The rest are learned as you level.")


def cmd_levels(cfg: Config, args) -> None:
    img = Screen.load(cfg.data_dir).grab()
    reader = SkillReader.load(cfg.layout, cfg.data_dir)
    for skill in SKILLS:
        print(f"{skill:>13}: {reader.read(img, skill)}")


def cmd_debug(cfg: Config, args) -> None:
    """Save an annotated screenshot showing everything the bot detects."""
    img = vision.load_png(args.image) if args.image else Screen.load(cfg.data_dir).grab()
    out = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    lay = cfg.layout

    def box(r, color, label=None):
        cv2.rectangle(out, (r.x, r.y), (r.x + r.w, r.y + r.h), color, 1)
        if label:
            cv2.putText(out, label, (r.x, r.y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

    box(lay.viewport, (255, 255, 255))
    targets = [("bank", cfg.bank_color)] + [(s.name, s.target) for s in cfg.plan]
    targets += [(f"route {n}", c) for n, cs in cfg.routes.items() for c in cs]
    for label, color in targets:
        for b in vision.find_blobs(img, color, cfg.color_tolerance, region=lay.viewport):
            box(b.rect, (0, 255, 0), label[:14])
    inv = Inventory(lay, cfg.items, tolerance=cfg.color_tolerance)
    tags = inv.tags(img)
    for i in range(SLOTS):
        box(lay.slot(i), (0, 0, 255) if i in tags else (160, 160, 160), tags.get(i, "")[:7])
    if args.skills:
        reader = SkillReader.load(lay, cfg.data_dir)
        for i, skill in enumerate(SKILLS):
            level = reader.read(img, skill)
            box(lay.skill_level(i), (0, 255, 255), "?" if level is None else str(level))
    if args.bank:
        for i in range(lay.bank_columns * 4):
            box(lay.bank_slot(i), (255, 0, 255), str(i))
    for name, pt in lay.tabs.items():
        cv2.circle(out, pt, 4, (255, 255, 0), 1)
    for i, pt in enumerate(lay.combat_styles):
        cv2.putText(out, str(i), pt, cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)
    box(lay.hp_bar, (0, 128, 255), "hp")
    for pt in lay.fingerprint_points:
        cv2.circle(out, pt, 3, (0, 128, 255), 1)
    cv2.circle(out, lay.compass, 4, (255, 255, 0), 1)
    cv2.circle(out, lay.run_orb, 5, (0, 255, 255), 1)
    cv2.imwrite(args.out, out)
    from .combat import CombatTask
    hp = CombatTask.hp_fraction(img, lay.hp_bar, cfg.hp_bar_color, cfg.color_tolerance)
    print(f"wrote {args.out}\ntagged slots: {tags}\nhp bar: {hp:.0%}")


def cmd_run(cfg: Config, args) -> None:
    import pyautogui

    from .controls import Controls
    handler = logging.handlers.RotatingFileHandler(cfg.data_dir / "skillbot.log",
                                                   maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    screen = Screen.load(cfg.data_dir)
    game = Game(cfg, screen, Controls(screen), Inventory(cfg.layout, cfg.items,
                                                         tolerance=cfg.color_tolerance))
    if cfg.run == "always":
        game.run = RunManager.load(game, cfg.data_dir)
    levels = Levels.load(game, SkillReader.load(cfg.layout, cfg.data_dir), cfg.data_dir)
    planner = Planner(game, levels, Session.load(game, cfg.data_dir))
    logging.info("starting; move the mouse to a screen corner to stop")
    try:
        planner.run()
    except StopBot as e:
        logging.info("stopped: %s", e)
    except pyautogui.FailSafeException:
        logging.info("stopped by failsafe")
    except KeyboardInterrupt:
        logging.info("stopped")
    logging.info("levels: %s", levels.levels)
    if game.run:
        logging.info("run: %s", game.run.stats)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="skillbot")
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="record where the game is and what logged in looks like")
    c.add_argument("--origin", type=int, nargs=2, metavar=("X", "Y"))
    sub.add_parser("calibrate-run", help="record the run orb's on/off colors")
    sub.add_parser("learn-digits", help="teach the level font from the open skills tab")
    sub.add_parser("levels", help="print the levels read from the open skills tab")
    c = sub.add_parser("debug", help="write an annotated screenshot")
    c.add_argument("--image", help="annotate this PNG instead of the live screen")
    c.add_argument("--skills", action="store_true", help="show skills-tab level boxes")
    c.add_argument("--bank", action="store_true", help="show bank slot numbers")
    c.add_argument("--out", default="debug.png")
    sub.add_parser("run", help="work through the plan")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = Config.load(args.config) if Path(args.config).exists() else Config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    {"calibrate": cmd_calibrate, "calibrate-run": cmd_calibrate_run, "learn-digits": cmd_learn_digits, "levels": cmd_levels,
     "debug": cmd_debug, "run": cmd_run}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
