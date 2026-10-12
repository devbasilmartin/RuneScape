# The plan: priorities

Agreed with the owner (Oct 2026). **F2P only for now**: the members methods, minigames and
slayer that already exist stay as they are; no new members work until the F2P game runs
well. Built in this order.

## Done

- **Schedules engine + panel** ([schedules.md](schedules.md)). Library methods only; one
  activity = a one-entry schedule; per entry minutes / until level / bank-drop (gathering
  and combat); the method's upper level ignored, lower enforced; repeat once / forever /
  N hours (finish the inventory) then log out; out of supplies or can't start → skip and
  notify; watching vs unattended with trust badges; saved by name, shared by accounts.
- **Cows** on the real client: fight, eat below 50% HP, drop or bank hides and beef, wait
  for respawns, don't start a second fight.
- **Send to PC** ([file-sharing.md](file-sharing.md)) and **Record**
  ([recording.md](recording.md)): screenshots, logs and videos to the PC, `frames.png`
  for Claude.
- **HP guard** for every activity ([safety.md](safety.md#low-hp-every-activity)): eats
  below half HP (the activity's food or any known food); no food and being hit (or below
  20%) → gets away, logs out, stops with the reason; steady low HP carries on; 2 escapes
  on an activity in two weeks → skipped until past that level.
- **F2P travel** ([travel.md](travel.md)): places by world coordinate
  (`library/places/f2p.yaml`), the bot knows which one it's at, sets a Shortest Path target
  on the world map from the map's measured scale (dragging the map for far places), climbs
  the Lumbridge castle stairs. F2P library methods have their banks. Not yet tried on the
  real client: owner sets up Shortest Path, marks the stairs, runs Calibrate map.
- **Run from the phone**: Discord `/run <activity>` and `/stoprun`, through the control
  panel ([discord.md](discord.md)); waits on the owner setting Discord up.

## Next

1. **Owner, at the VM**: shared folder, try Record, log the VM into GitHub then make the
   repo private, teach the digit 9 (Teach levels with a 9 on the skills tab), set up
   Discord ([discord.md](discord.md)).
2. **F2P mode**: library methods tagged F2P or members; an account's type and default
   mode (F2P progression, or a saved schedule); rotation turns run the account's mode and
   resume a schedule where it left off; combat gates for spots with aggressive monsters
   (Draynor willows: dark wizards, about combat 41).
3. **Cows + fire cooking**: kill cows, loot raw beef (no hides), chop one log, light it,
   find the fire by its color next to the player (a one-time "Teach fire" button records
   the flames), cook on it, keep ~5 cooked as food, drop the rest and burnt; relight when
   the fire is lost; after 3 failed relights pause cooking 30 min (keep fighting) and
   notify. Axe and tinderbox stay in the inventory, untagged.
4. **More F2P methods**, each tried on the real client: fishing (shrimp → fly fishing),
   power-mining copper/tin → iron, firemaking lines, cooking at a range.

Small fixes, whenever the owner is at the VM: run energy's "1" (`energy-check.png`), the
software cursor.

## Later

- **Members**: try the already-built members methods, minigames and slayer on the real
  client, one at a time through the trust levels; fletching and stringing.
