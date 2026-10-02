"""Command line: python -m skillbot <command>; see --help."""
import argparse
import json
import logging
import logging.handlers

import cv2

from . import vision
from .config import Config
from .game import Game, StopBot
from .inventory import SLOTS, Inventory
from .notify import notify
from .notify import setup as notify_setup
from .planner import Levels, Planner
from .digits import GlyphBook
from .run import EnergyReader, RunManager, orb_sample
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


def cmd_learn_energy(cfg: Config, args) -> None:
    screen = Screen.load(cfg.data_dir)
    book = GlyphBook.load(cfg.data_dir / "energy_digits.json")
    reader = EnergyReader(cfg.layout.run_energy_box, book)
    import time
    value = None
    print("Run around (or stand still with run off) so the energy keeps changing. "
          "Ctrl+C to finish.")
    try:
        while not book.complete():
            img = screen.grab()
            if value is not None:
                value = reader.read(img, value, window=1)
            if value is None:
                text = input("  type the run energy shown next to the orb: ").strip()
                if not text.isdigit() or not reader.learn(screen.grab(), int(text)):
                    print("    could not split the number into that many digits; "
                          "check layout.run_energy_box with `debug`")
                    continue
                value = int(text)
                print(f"  watching... known digits: {book.known_digits()}")
            book.save()
            time.sleep(0.2)          # faster than the game changes the number
    except KeyboardInterrupt:
        pass
    book.save()
    print(f"\nknown digits: {book.known_digits() or 'none'}")


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
    energy = EnergyReader(lay.run_energy_box,
                          GlyphBook.load(cfg.data_dir / "energy_digits.json")).read(img)
    box(lay.run_energy_box, (0, 255, 255), f"run {energy if energy is not None else '?'}")
    cv2.imwrite(args.out, out)
    from .combat import CombatTask
    hp = CombatTask.hp_fraction(img, lay.hp_bar, cfg.hp_bar_color, cfg.color_tolerance)
    print(f"wrote {args.out}\ntagged slots: {tags}\nhp bar: {hp:.0%}")


def cmd_doctor(cfg: Config, args) -> None:
    from .doctor import report, run_checks
    raise SystemExit(report(run_checks(cfg)))


def cmd_supervise(cfg: Config, args) -> None:
    from .supervisor import Host, Supervisor, SupervisorConfig
    handler = logging.handlers.RotatingFileHandler(cfg.data_dir / "supervisor.log",
                                                   maxBytes=2_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    sup_cfg = SupervisorConfig.from_dict(cfg.supervisor)
    host = Host(args.config, cfg.data_dir, profile=args.selected.name)
    raise SystemExit(Supervisor(sup_cfg, host, cfg.data_dir).run())


def cmd_discord(cfg: Config, args) -> None:
    from .discord_bot import run
    handler = logging.handlers.RotatingFileHandler(cfg.data_dir / "discord.log",
                                                   maxBytes=2_000_000, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    run(args.profiles, cfg.data_dir if args.selected.name is None else None,
        summary_hour=int(cfg.discord.get("summary_hour", 9)))


def cmd_ask(cfg: Config, args) -> None:
    """Send a test question through Discord and wait for the answer."""
    import time

    from .messages import Mailbox
    box = Mailbox(args.mailbox_dir)
    ask_id = box.ask(args.question, args.options or ["Yes", "No"])
    print("asked; answer it in Discord (Ctrl+C to give up)...")
    while (answer := box.answer(ask_id)) is None:
        time.sleep(2)
    print(f"answer: {answer}")


def cmd_setup(cfg: Config, args) -> None:
    from .colors import Registry
    from .setup_check import find_step, setup_text
    print(setup_text(cfg, find_step(cfg, args.step), Registry.load(cfg.colors_file)))


def cmd_check_setup(cfg: Config, args) -> None:
    from .colors import Registry
    from .doctor import report
    from .setup_check import check_setup, find_step
    img = vision.load_png(args.image) if args.image else Screen.load(cfg.data_dir).grab()
    checks = check_setup(cfg, find_step(cfg, args.step), img, Registry.load(cfg.colors_file))
    raise SystemExit(report(checks))


def cmd_colors(cfg: Config, args) -> None:
    from .colors import Registry
    from .setup_check import colors_text
    print(colors_text(Registry.load(cfg.colors_file), cfg.color_tolerance))


def cmd_profile(cfg: Config, args) -> None:
    import subprocess
    profiles = args.profiles
    if args.action == "list":
        active = profiles.active()
        for name in profiles.names():
            print(("* " if name == active else "  ") + name)
        if not profiles.names():
            print("no profiles yet: python -m skillbot profile create NAME")
    elif args.action == "create":
        folder = profiles.create(args.name)
        env = profiles.env_dir / f"{args.name}.env"
        print(f"created {folder}. Put this account's login in {env}:\n"
              f'  SKILLBOT_USERNAME="..."\n  SKILLBOT_PASSWORD="..."\n'
              f"Then calibrate it: python -m skillbot --profile {args.name} calibrate")
    elif args.action == "use":
        profiles.use(args.name)
        print(f"active profile: {args.name}")
        state = subprocess.run(["systemctl", "--user", "is-active", "skillbot.service"],
                               capture_output=True, text=True).stdout.strip()
        if state == "active":
            subprocess.run(["systemctl", "--user", "restart", "skillbot.service"], check=False)
            print("restarted the supervisor with this profile")


def cmd_pause(cfg: Config, args) -> None:
    (cfg.data_dir / "paused").write_text("")
    print("paused: the supervisor stops the bot within ~15s. Switch RuneLite to your own "
          "profile if you're going to play. `python -m skillbot resume` to hand back.")


def cmd_resume(cfg: Config, args) -> None:
    (cfg.data_dir / "paused").unlink(missing_ok=True)
    print("resumed: switch RuneLite back to the `bot` profile; the supervisor starts the bot "
          "within ~15s.")


def cmd_run(cfg: Config, args) -> None:
    import pyautogui

    from .controls import Controls
    from .heartbeat import Heartbeat
    handler = logging.handlers.RotatingFileHandler(cfg.data_dir / "skillbot.log",
                                                   maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    screen = Screen.load(cfg.data_dir)
    controls = Controls(screen)
    screen.heartbeat = controls.heartbeat = Heartbeat(cfg.data_dir / "heartbeat.json")
    game = Game(cfg, screen, controls, Inventory(cfg.layout, cfg.items,
                                                 tolerance=cfg.color_tolerance))
    if cfg.run == "always":
        game.run = RunManager.load(game, cfg.data_dir)
    levels = Levels.load(game, SkillReader.load(cfg.layout, cfg.data_dir), cfg.data_dir)
    planner = Planner(game, levels, Session.load(game, cfg.data_dir), status_dir=cfg.data_dir)
    logging.info("starting; move the mouse to a screen corner to stop")
    try:
        planner.run()
    except StopBot as e:
        logging.info("stopped: %s", e)
        notify(f"stopped: {e}")
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
    p.add_argument("-p", "--profile", help="account profile (default: the active one)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="record where the game is and what logged in looks like")
    c.add_argument("--origin", type=int, nargs=2, metavar=("X", "Y"))
    sub.add_parser("calibrate-run", help="record the run orb's on/off colors")
    sub.add_parser("learn-energy", help="teach the run energy number's digits")
    sub.add_parser("learn-digits", help="teach the level font from the open skills tab")
    sub.add_parser("levels", help="print the levels read from the open skills tab")
    c = sub.add_parser("debug", help="write an annotated screenshot")
    c.add_argument("--image", help="annotate this PNG instead of the live screen")
    c.add_argument("--skills", action="store_true", help="show skills-tab level boxes")
    c.add_argument("--bank", action="store_true", help="show bank slot numbers")
    c.add_argument("--out", default="debug.png")
    sub.add_parser("doctor", help="check this machine is ready for the bot")
    sub.add_parser("supervise", help="run the client and the bot, restarting them as needed")
    sub.add_parser("discord", help="run the Discord service (notifications, questions, commands)")
    c = sub.add_parser("ask", help="send a test question through Discord")
    c.add_argument("question")
    c.add_argument("options", nargs="*")
    c = sub.add_parser("setup", help="what to mark in RuneLite for a plan step")
    c.add_argument("step", help="step name or number")
    c = sub.add_parser("check-setup", help="verify a step's highlights from a screenshot")
    c.add_argument("step", help="step name or number")
    c.add_argument("--image", help="check this PNG instead of the live screen")
    sub.add_parser("colors", help="the color registry and free colors")
    c = sub.add_parser("profile", help="list, create or switch account profiles")
    c.add_argument("action", choices=["list", "create", "use"])
    c.add_argument("name", nargs="?")
    sub.add_parser("pause", help="stop the bot (supervisor keeps it stopped) so you can play")
    sub.add_parser("resume", help="hand control back to the bot")
    sub.add_parser("run", help="work through the plan")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    from .profiles import Profiles
    args.profiles = profiles = Profiles()
    if args.cmd == "profile" and args.action != "list" and not args.name:
        p.error(f"profile {args.action} needs a NAME")
    try:
        args.selected = sel = profiles.select(args.profile, args.config)
    except ValueError as e:
        p.error(str(e))
    args.config = str(sel.config_path)
    cfg = Config.load(sel.config_path) if sel.config_path.exists() else Config()
    if sel.data_dir is not None:
        cfg.data_dir = sel.data_dir
        profiles.load_env(sel.name)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    args.mailbox_dir = profiles.shared_data if sel.name else cfg.data_dir
    notify_setup(args.mailbox_dir, tag=sel.name)
    {"calibrate": cmd_calibrate, "calibrate-run": cmd_calibrate_run,
     "learn-energy": cmd_learn_energy, "learn-digits": cmd_learn_digits, "levels": cmd_levels,
     "debug": cmd_debug, "doctor": cmd_doctor, "supervise": cmd_supervise, "discord": cmd_discord, "ask": cmd_ask,
     "setup": cmd_setup, "check-setup": cmd_check_setup, "colors": cmd_colors,
     "profile": cmd_profile, "pause": cmd_pause,
     "resume": cmd_resume, "run": cmd_run}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
