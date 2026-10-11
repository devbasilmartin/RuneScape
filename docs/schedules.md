# One activity and schedules

Pick what the bot does from the method library (`library/*.yaml`), in the control panel's
**Run** card, or from a terminal.

## One activity

Do one thing, past its usual level range, until a time and/or level, then log out:

```sh
python -m skillbot run --supervised --activity oaks_draynor --minutes 60
python -m skillbot run --activity willows_draynor --until-level 45 --when-full bank
```

Leave both limits out to run until you stop it. The method's lower level still applies
(no willows at woodcutting 20).

## Schedules

Several activities in order, each for its minutes or until its level (whichever comes
first). Saved by name in `schedules/` and shared by every account:

```yaml
# schedules/oak loop.yaml
repeat: {hours: 3}          # once (then log out) | forever | {hours: N}
entries:
  - method: oaks_draynor
    minutes: 60
    when_full: bank         # gathering/combat: bank | drop (default: the method's)
  - method: burn_willows
    minutes: 30
```

```sh
python -m skillbot run --supervised --schedule "oak loop"
```

- An activity that **runs out of supplies** early, or **can't start** (level too low,
  nothing to work with), is skipped: you're told (Discord, if set up) and the schedule
  moves on. It gets as much done as the supplies allow.
- **Repeat once** logs out after the last activity. **For N hours** cycles until the time
  is up, finishes the current inventory, then logs out. **Forever** runs until you stop it
  (and stops if a whole cycle couldn't do anything).
- **Bank or drop** applies to gathering and combat (drop: hides are dropped when the
  inventory fills; it never goes to the bank, so running out of food ends the activity
  and the run logs out). Combat eats below 50% HP: cooked meat, shrimps, anchovies or
  trout, whichever you carry, and reads your HP from RuneLite's Status Bars. Banking needs the bank marked (see
  [markers.md](markers.md)); where it's out of view from the activity, a route of marked
  tiles too. A bank/drop choice other than the method's default is its own activity for
  trust: it earns its "proven" status separately.

## Watching or unattended

The panel's **I'm watching** box (or `--supervised`): new activities run too, and the bot
stops at the first error. **Unattended**, an activity that hasn't yet run 2 hours cleanly
while watched is skipped, like one out of supplies. Each activity shows its status: new,
trial or trusted (see `skillbot/trust.py`).
