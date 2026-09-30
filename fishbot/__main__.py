"""Command line entry point: python -m fishbot {calibrate,debug,run}."""
import argparse
import json
import logging
from pathlib import Path

import cv2

from . import vision
from .bot import BotError, FishingBot
from .config import Config
from .inventory import SLOTS, Inventory
from .screen import Screen


def cmd_calibrate(cfg: Config, args) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    if args.origin:
        origin = tuple(args.origin)
    else:
        import pyautogui
        input("Put RuneLite in FIXED mode. Hover the mouse over the top-left pixel of the game "
              "canvas (not the window title bar) and press Enter...")
        origin = tuple(pyautogui.position())
    (cfg.data_dir / "origin.json").write_text(json.dumps({"origin": origin}))
    print(f"canvas origin = {origin}. Run `python -m fishbot debug` to check it.")


def cmd_debug(cfg: Config, args) -> None:
    """Save an annotated screenshot showing everything the bot detects."""
    route_colors = {tuple(c) for colors in cfg.routes.values() for c in colors}
    img = vision.load_png(args.image) if args.image else Screen.load(cfg.data_dir).grab()
    out = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    lay = cfg.layout
    vp = lay.viewport
    cv2.rectangle(out, (vp.x, vp.y), (vp.x + vp.w, vp.y + vp.h), (255, 255, 255), 1)
    targets = [("spot", cfg.fishing_color), ("bank", cfg.bank_color), ("cook", cfg.cook_color)]
    targets += [(f"tile{c}", c) for c in sorted(route_colors)]
    for label, color in targets:
        for b in vision.find_blobs(img, color, cfg.color_tolerance, region=vp):
            cv2.rectangle(out, (b.x, b.y), (b.x + b.w, b.y + b.h), (0, 255, 0), 2)
            cv2.putText(out, label, (b.x, b.y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    inv = Inventory(lay, cfg.items, cfg.tools, cfg.color_tolerance)
    tags = inv.tags(img)
    for i in range(SLOTS):
        s = lay.slot(i)
        color = (0, 0, 255) if i in tags else (160, 160, 160)
        cv2.rectangle(out, (s.x, s.y), (s.x + s.w, s.y + s.h), color, 1)
        if i in tags:
            cv2.putText(out, tags[i][:7], (s.x, s.y + s.h - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.28,
                        (0, 0, 255), 1)
    cv2.circle(out, lay.compass, 4, (255, 255, 0), 1)
    cv2.imwrite(args.out, out)
    print(f"wrote {args.out}")
    print(f"tagged slots: {tags}  full={inv.is_full(img)}")


def cmd_run(cfg: Config, args) -> None:
    import pyautogui

    from .controls import Controls
    screen = Screen.load(cfg.data_dir)
    inv = Inventory(cfg.layout, cfg.items, cfg.tools, cfg.color_tolerance)
    bot = FishingBot(cfg, screen, Controls(screen), inv)
    logging.info("starting in %s mode; move the mouse to a screen corner to stop", cfg.mode)
    try:
        bot.run()
    except pyautogui.FailSafeException:
        logging.info("stopped by failsafe")
    except BotError as e:
        logging.error("stopping: %s", e)
    except KeyboardInterrupt:
        logging.info("stopped")
    logging.info("stats: %s", bot.stats)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="fishbot")
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="record where the game canvas is on screen")
    c.add_argument("--origin", type=int, nargs=2, metavar=("X", "Y"))
    c = sub.add_parser("debug", help="write an annotated screenshot")
    c.add_argument("--image", help="annotate this PNG instead of the live screen")
    c.add_argument("--out", default="debug.png")
    sub.add_parser("run", help="start the bot")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = Config.load(args.config) if Path(args.config).exists() else Config()
    {"calibrate": cmd_calibrate, "debug": cmd_debug, "run": cmd_run}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
