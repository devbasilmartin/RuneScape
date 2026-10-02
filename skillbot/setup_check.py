"""`setup STEP` prints exactly what to mark in RuneLite for a plan step; `check-setup
STEP` verifies it from a screenshot taken where the step runs."""
from .colors import Registry, distinct, palette
from .config import Config, Step
from .doctor import FAIL, PASS, WARN, Check
from .inventory import Inventory
from . import vision

RANDOM_EVENT_NPCS = ("Genie", "Drunken Dwarf", "Mysterious Old Man", "Drill Demon", "Evil Bob",
                     "Frog", "Gravedigger", "Rick Turpentine", "Sandwich lady", "Strange plant",
                     "Freaky Forester", "Beekeeper", "Bee keeper", "Quiz Master", "Pillory guard",
                     "Count Check", "Dr Jekyll", "Flippa", "Niles", "Miles", "Giles", "Postie Pete")

TARGET_PLUGIN = {
    "gather": "Object Markers on the resource (NPC Indicators for fishing spots)",
    "process": "Object Markers on the station",
    "firemaking": "Ground Markers on the first tile of the lane",
    "combat": "NPC Indicators on the monster (outline or hull, names off)",
    "runecraft": "Object Markers on the altar",
    "cast": "",
    "agility": "",
}


def find_step(cfg: Config, which: str) -> Step:
    if which.isdigit() and 1 <= int(which) <= len(cfg.plan):
        return cfg.plan[int(which) - 1]
    for step in cfg.plan:
        if step.name.lower() == which.lower():
            return step
    names = ", ".join(f"{i + 1}. {s.name}" for i, s in enumerate(cfg.plan))
    raise SystemExit(f"no step {which!r} in the plan; steps: {names}")


def describe(color, registry: Registry, item: bool = False) -> str:
    hexcode = "#{:02X}{:02X}{:02X}".format(*color)
    name = registry.name_of(color, item=item)
    return f"{name} {hexcode}" if name else hexcode


def banks(step: Step) -> bool:
    return (step.when_full == "bank" and step.task in ("gather", "combat")) or bool(step.withdraw) \
        or step.task in ("runecraft", "process")


def setup_text(cfg: Config, step: Step, registry: Registry) -> str:
    d = lambda c: describe(c, registry)      # noqa: E731
    lines = [f"Setup for step {step.name!r} ({step.skill}, {step.task})", "",
             "RuneLite `bot` profile, colors exact and fully opaque:"]
    if step.target is not None:
        lines.append(f"  • {TARGET_PLUGIN[step.task]}: {d(step.target)}")
    if step.obstacles:
        lines.append("  • Object Markers on each obstacle, in course order:")
        lines += [f"      {i + 1}. {d(c)}" for i, c in enumerate(step.obstacles)]
    if step.spell:
        lines.append(f"  • Spell at {list(step.spell)} in the magic tab (check with debug)")
    if step.process and step.process.get("target"):
        lines.append(f"  • Object Markers on the station for processing each load: "
                     f"{d(tuple(step.process['target']))}")
    if banks(step):
        lines.append(f"  • Object Markers on the bank booth/chest: {d(cfg.bank_color)}")
    if step.loot:
        lines.append(f"  • Ground Items: highlight the loot you want, Highlight tiles on: "
                     f"{d(step.loot)}")
    if step.ruins:
        lines.append(f"  • Object Markers on the Mysterious ruins: {d(step.ruins)}")
    if step.portal:
        lines.append(f"  • Object Markers on the altar's exit portal: {d(step.portal)}")
    if step.task == "combat":
        lines.append(f"  • Status Bars: Hitpoints on the left of the inventory: "
                     f"{d(cfg.hp_bar_color)}")
    if cfg.danger_color:
        lines.append(f"  • NPC Indicators on random-event NPCs ({', '.join(RANDOM_EVENT_NPCS[:5])}, "
                     f"...): {d(cfg.danger_color)}")
    for label, color, how in (
            ("Genie", cfg.genie_color, "NPC Indicators on Genie"),
            ("grave", cfg.grave_color, "NPC Indicators on Grave"),
            ("respawn", cfg.respawn_color, "Ground Marker on your respawn tile"),
            ("others", cfg.other_player_color, "Player Indicators, highlight others")):
        if color:
            lines.append(f"  • {how}: {d(color)}")
    for role, route in step.walk.items():
        tiles = " → ".join(d(t) for t in cfg.routes.get(route, []))
        lines.append(f"  • Ground Markers for route {route!r} ({role}), in walking order: {tiles}")
    tagged = list(dict.fromkeys(list(step.items) + list(step.runes)
                                + ([step.on_item] if step.on_item else [])
                                + list(step.food) + list(step.bury)
                                + list(step.keep) + ([step.enter_with] if step.enter_with else [])
                                + ([step.use_item] if step.use_item not in (None, "any") else [])
                                + list((step.process or {}).get("items", []))))
    if tagged:
        lines.append("  • Inventory Tags:")
        lines += [f"      {name}: {describe(cfg.items[name], registry, item=True)}"
                  for name in tagged]
    lines += ["", "In game:"]
    lines.append("  • Fixed mode, camera zoomed all the way out")
    if step.task == "gather" and step.when_full == "drop":
        lines.append("  • Shift-click drop on")
    if banks(step):
        lines.append("  • Esc closes the current interface; bank quantity set as the step needs")
    if step.bank_tab:
        lines.append(f"  • Bank Tags: a tag {step.bank_tab!r} on this step's items, with "
                     "'Bank tag layouts' arranging them; bank placeholders on")
    for w in step.withdraw:
        what = w.item or "(unchecked item)"
        qty = f", quantity {w.quantity}" if w.quantity else ""
        where = f"tab {step.bank_tab!r}" if step.bank_tab else "the bank"
        lines.append(f"  • Withdraw: slot {w.slot} of {where}: {what}{qty}")
    untagged = step.tools
    if untagged:
        lines.append(f"  • {untagged} untagged tool slot(s) in the inventory (net, axe, tinderbox...)")
    lines += ["", f"Then stand where the step runs and: python -m skillbot check-setup "
                  f"\"{step.name}\""]
    return "\n".join(lines)


def check_setup(cfg: Config, step: Step, img, registry: Registry) -> list[Check]:
    tol, region = cfg.color_tolerance, cfg.layout.viewport

    def seen(color):
        return vision.find_blobs(img, color, tol, region=region)

    d = lambda c: describe(c, registry)      # noqa: E731
    checks = []
    blobs = seen(step.target) if step.target is not None else None
    if step.obstacles:
        first = seen(step.obstacles[0])
        checks.append(Check("first obstacle", PASS if first else WARN,
                            f"{d(step.obstacles[0])} visible" if first else
                            f"{d(step.obstacles[0])} not visible: stand at the course start"))
    if step.target is None:
        pass
    elif blobs:
        checks.append(Check("target", PASS, f"{len(blobs)} × {d(step.target)} visible"))
    else:
        checks.append(Check("target", FAIL, f"no {d(step.target)} on screen: check the marker "
                                            "exists and its color is exactly this, fully opaque"))
    optional = {"bank": cfg.bank_color if banks(step) else None, "loot": step.loot,
                "ruins": step.ruins, "portal": step.portal}
    for role, route in step.walk.items():
        for i, tile in enumerate(cfg.routes.get(route, [])):
            optional[f"route {route} tile {i + 1}"] = tile
    for label, color in optional.items():
        if color is None:
            continue
        found = seen(color)
        checks.append(Check(label, PASS if found else WARN,
                            f"{d(color)} visible" if found else
                            f"{d(color)} not visible from here (fine if it's elsewhere)"))
    if cfg.danger_color and seen(cfg.danger_color):
        checks.append(Check("random event", WARN, "a random-event NPC is on screen"))
    tags = Inventory(cfg.layout, cfg.items, tolerance=tol).tags(img)
    wanted = set(step.items) | set(step.food) | set(step.keep) | (
        {step.enter_with} if step.enter_with else set()) | (
        {step.with_item} if step.with_item else set())
    present = sorted(set(tags.values()) & wanted)
    checks.append(Check("inventory tags", PASS if present else WARN,
                        f"tagged in inventory: {', '.join(present)}" if present else
                        "none of this step's items are in the inventory right now"))
    return checks


def colors_text(registry: Registry, tolerance: int) -> str:
    lines = []
    by_cat = {}
    for e in registry.entries.values():
        by_cat.setdefault(e.category, []).append(e)
    for cat, entries in by_cat.items():
        lines.append(f"{cat}:")
        lines += [f"  {e.name:<16} #{e.rgb[0]:02X}{e.rgb[1]:02X}{e.rgb[2]:02X}  {list(e.rgb)}"
                  for e in entries]
    problems = registry.check(tolerance)
    lines.append("")
    lines.append("problems: " + ("; ".join(problems) if problems else "none"))
    world = [e.rgb for e in registry.entries.values() if e.category != "item"]
    free = [c for c in palette(tolerance) if all(distinct(c, w, tolerance) for w in world)]
    lines.append(f"free colors for new world highlights ({len(free)}): " +
                 ", ".join("#{:02X}{:02X}{:02X}".format(*c) for c in free[:24]))
    return "\n".join(lines)
