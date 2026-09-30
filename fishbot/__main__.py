"""Command line entry point: python -m fishbot {calibrate,capture-item,capture-region,debug,run}."""
import argparse
import json
import logging
from pathlib import Path

import cv2

from . import vision
from .bot import BotError, FishingBot
from .config import Config
from .inventory import SLOTS, Inventory
from .layout import Rect
from .screen import Screen


def cmd_calibrate(cfg: Config, args) -> None:
    import pyautogui
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    if args.origin:
        origin = tuple(args.origin)
    else:
        input("Put RuneLite in FIXED mode. Hover the mouse over the top-left pixel of the game "
              "canvas (not the window title bar) and press Enter...")
        origin = tuple(pyautogui.position())
    (cfg.data_dir / "origin.json").write_text(json.dumps({"origin": origin}))
    print(f"canvas origin = {origin}")
    screen = Screen(origin)
    name = "inv_baseline_bank.png" if args.bank else "inv_baseline.png"
    what = "the bank open (quantity set to All)" if args.bank else "the inventory tab open"
    input(f"With {what} and ONLY your tools in the inventory (tool slots {list(cfg.tool_slots)}), "
          "press Enter...")
    vision.save_png(cfg.data_dir / name, cfg.layout.inventory.crop(screen.grab()))
    print(f"saved {cfg.data_dir / name}. Run `python -m fishbot debug` to check the result.")


def cmd_capture_item(cfg: Config, args) -> None:
    img = Screen.load(cfg.data_dir).grab()
    slot = cfg.layout.slot(args.slot)
    inner = Rect(slot.x + 3, slot.y + 3, slot.w - 6, slot.h - 6)  # margin tolerates small shifts
    out = cfg.data_dir / "items" / f"{args.name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    vision.save_png(out, inner.crop(img))
    print(f"saved {out}")


def cmd_capture_region(cfg: Config, args) -> None:
    img = Screen.load(cfg.data_dir).grab()
    out = cfg.data_dir / f"{args.name}.png"
    vision.save_png(out, Rect(*args.rect).crop(img))
    print(f"saved {out}")


def cmd_debug(cfg: Config, args) -> None:
    """Save an annotated screenshot showing everything the bot detects."""
    img = vision.load_png(args.image) if args.image else Screen.load(cfg.data_dir).grab()
    out = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    lay = cfg.layout
    vp = lay.viewport
    cv2.rectangle(out, (vp.x, vp.y), (vp.x + vp.w, vp.y + vp.h), (255, 255, 255), 1)
    for label, color in (("spot", cfg.fishing_color), ("bank", cfg.bank_color),
                         ("cook", cfg.cook_color)):
        for b in vision.find_blobs(img, color, cfg.color_tolerance, region=vp):
            cv2.rectangle(out, (b.x, b.y), (b.x + b.w, b.y + b.h), (0, 255, 0), 2)
            cv2.putText(out, label, (b.x, b.y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    inv = None
    if (cfg.data_dir / "inv_baseline.png").exists():
        inv = Inventory.load(lay, cfg.data_dir, tool_slots=cfg.tool_slots)
    for i in range(SLOTS):
        s = lay.slot(i)
        new = inv is not None and inv.is_new(img, i)
        color = (0, 0, 255) if new else ((255, 128, 0) if i in cfg.tool_slots else (160, 160, 160))
        cv2.rectangle(out, (s.x, s.y), (s.x + s.w, s.y + s.h), color, 1)
        name = inv.identify(img, i) if new else None
        if name:
            cv2.putText(out, name[:6], (s.x, s.y + s.h - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.28,
                        (0, 0, 255), 1)
    mx, my = lay.minimap_center
    cv2.circle(out, (mx, my), 3, (0, 255, 255), -1)
    for route, points in cfg.routes.items():
        for dx, dy in points:
            cv2.circle(out, (mx + dx, my + dy), 3, (255, 0, 255), -1)
    cv2.circle(out, lay.compass, 4, (255, 255, 0), 1)
    cv2.imwrite(args.out, out)
    print(f"wrote {args.out}")
    if inv is not None:
        print(f"new items in slots: {inv.new_slots(img)}  full={inv.is_full(img)}")


def cmd_run(cfg: Config, args) -> None:
    import pyautogui

    from .controls import Controls
    screen = Screen.load(cfg.data_dir)
    inv = Inventory.load(cfg.layout, cfg.data_dir, tool_slots=cfg.tool_slots)
    bank_tmpl = cfg.data_dir / "bank_open.png"
    bot = FishingBot(cfg, screen, Controls(screen), inv,
                     bank_template=vision.load_png(bank_tmpl) if bank_tmpl.exists() else None)
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
    c = sub.add_parser("calibrate", help="record canvas position and empty-inventory baseline")
    c.add_argument("--origin", type=int, nargs=2, metavar=("X", "Y"))
    c.add_argument("--bank", action="store_true", help="capture the baseline with the bank open")
    c = sub.add_parser("capture-item", help="save an inventory slot as an item template")
    c.add_argument("name")
    c.add_argument("slot", type=int)
    c = sub.add_parser("capture-region", help="save a canvas region, e.g. bank_open")
    c.add_argument("name")
    c.add_argument("rect", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    c = sub.add_parser("debug", help="write an annotated screenshot")
    c.add_argument("--image", help="annotate this PNG instead of the live screen")
    c.add_argument("--out", default="debug.png")
    sub.add_parser("run", help="start the bot")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = Config.load(args.config) if Path(args.config).exists() else Config()
    {"calibrate": cmd_calibrate, "capture-item": cmd_capture_item,
     "capture-region": cmd_capture_region, "debug": cmd_debug, "run": cmd_run}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
