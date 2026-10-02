"""The routine language: what a `task: routine` step may contain (checked at load time).

A routine is a list of blocks, run top to bottom once per batch:

    - name: mine                      # for logs and errors
      when: {visible: ore_vein}       # skip the block unless this holds
      repeat_until: {full: true}      # run `do` again and again until this holds
      until_fail: true                # ...or until a wait_for in `do` times out
      max: 50                         # safety cap on repetitions
      count: deposits                 # +1 to a counter each time the block runs
      reset: [deposits]               # counters set back to 0 after the block
      exhausted_if: {lacks: rune_essence}   # end the step (out of supplies)
      do:
        - click: ore_vein             # nearest highlight; or {item: name} / {point: [x, y]}
        - wait_for: {gained: paydirt} # condition, with `timeout` (default 20 s)
          timeout: 30

Actions: click (optionally right_option: N), use {item, target}, key, type, wait,
wait_for, bank, drop, travel / walk (with until: color), cast {spell, on_item},
dialog [options], tab, notify, progress. (Never use a bare `on:` key: YAML reads it
as true.)
Conditions (all keys must hold): visible, not_visible, near, has, lacks,
count_at_least {item: n}, full, hp_below, counter_at_least {name: n}, gained, lost,
any [conditions].
"""

ACTIONS = {"click", "use", "key", "type", "wait", "wait_for", "bank", "drop", "travel",
           "walk", "cast", "dialog", "tab", "notify", "progress"}
ACTION_OPTIONS = {"timeout", "right_option", "avoid_danger", "until", "on_item"}
CONDITIONS = {"visible", "not_visible", "near", "has", "lacks", "count_at_least", "full",
              "hp_below", "counter_at_least", "gained", "lost", "any"}
BLOCK_KEYS = {"name", "when", "repeat_until", "until_fail", "max", "count", "reset",
              "exhausted_if", "do"}


def check_condition(cond, where: str) -> None:
    if not isinstance(cond, dict) or not cond:
        raise ValueError(f"{where}: a condition must be a non-empty mapping")
    unknown = set(cond) - CONDITIONS
    if unknown:
        raise ValueError(f"{where}: unknown condition(s) {sorted(unknown)}")
    for sub in cond.get("any", []):
        check_condition(sub, where)


def check_action(action, where: str) -> None:
    if not isinstance(action, dict):
        raise ValueError(f"{where}: an action must be a mapping like {{click: bank}}")
    nested = [v for v in action.values() if isinstance(v, dict)]
    if any(True in d for d in [action] + nested):
        raise ValueError(f"{where}: a bare `on:` key reads as true in YAML; use target: "
                         "(for use) or until: (for travel/walk)")
    main = set(action) & ACTIONS
    if len(main) != 1:
        raise ValueError(f"{where}: each action needs exactly one of {sorted(ACTIONS)}")
    unknown = set(action) - ACTIONS - ACTION_OPTIONS
    if unknown:
        raise ValueError(f"{where}: unknown action option(s) {sorted(unknown)}")
    if "wait_for" in action:
        check_condition(action["wait_for"], where)


def check_routine(routine, step_name: str) -> None:
    if not isinstance(routine, list) or not routine:
        raise ValueError(f"step {step_name!r}: routine must be a non-empty list of blocks")
    for i, block in enumerate(routine):
        where = f"step {step_name!r} block {block.get('name', i + 1)!r}" \
            if isinstance(block, dict) else f"step {step_name!r} block {i + 1}"
        if not isinstance(block, dict) or "do" not in block:
            raise ValueError(f"{where}: needs a do: list")
        unknown = set(block) - BLOCK_KEYS
        if unknown:
            raise ValueError(f"{where}: unknown key(s) {sorted(unknown)}")
        for key in ("when", "repeat_until", "exhausted_if"):
            if key in block:
                check_condition(block[key], where)
        for action in block["do"]:
            check_action(action, where)
