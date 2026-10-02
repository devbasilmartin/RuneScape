# Semi-automatic Slayer

The bot can't read the chat, so **you tell it which monster** it was assigned; it does
everything else:

1. With no task, it travels to a Slayer master and picks **Assignment**.
2. It asks you on Discord: *"New Slayer task from Vannaka. Which monster?"* Tap a button or
   reply with the name. No Discord? `python -m skillbot slayer-task "hill giants"`.
3. While it waits, the planner trains other steps (goals mode rests Slayer for 30 minutes).
4. With your answer it travels to that monster and fights it with the step's food, style
   and loot settings until the **Slayer plugin's infobox disappears** (task finished).
5. Then it starts over.

Answers besides a monster:
- **skip**: get a new task from Turael instead (free, but resets your streak; spending points
  on skips is yours to do in the rewards shop).
- **mine**: you do this task yourself; the bot leaves Slayer alone until the infobox is gone.

Anything it doesn't know gets asked again. The bot's state (current monster, tasks done)
is in `data/slayer.json` and survives restarts.

## Setup

- **Slayer plugin** (built in): task infobox on. Keep it the **first** infobox (top left of the
  game) or set `layout.slayer_box` to where its number is; `debug` draws that box.
- `python -m skillbot learn-slayer` once while on a task: type the count, keep killing, it
  learns the digits as the count drops. The count only shows progress in status reports; the end
  of a task is the infobox disappearing, so this step is optional.
- **NPC Indicators**: Slayer masters in `slayer_master`; every monster from the list below in
  `enemy` (NPC Indicators takes a comma-separated list of names, so add them all once).
  Where two listed monsters share a spot (goblins near the Lumbridge cows) it may fight the
  wrong one now and then: harmless, but those kills don't count. Trim the list if that bothers you.
- Destinations (`add-destination`) for each master and monster you'll use; the names are in
  `library/slayer/slayer.yaml`.

```yaml
- name: slayer
  skill: slayer
  task: slayer
  until_level: 99
  food: [shark]
  eat_below: 0.5
  loot: loot
  bank_tab: food
  withdraw: [{slot: 1, item: shark, quantity: x}]
  vars: {master: vannaka}   # optional: otherwise the best master your combat level allows
```

In goals mode the library method `slayer` (in `library/combat.yaml`) trains Slayer like any other skill.

## Masters and monsters

`library/slayer/slayer.yaml` lists the masters (Turael → Vannaka → Chaeldar → Nieve → Duradel,
with their combat-level and quest requirements) and the monsters the bot knows to start with:
birds, cows, goblins, dwarves, minotaurs, hill and moss giants, lesser and greater demons, and fire
giants. To add one, give it a name, aliases, a destination and (optionally) step overrides such as
`stand_on` or different food. Brimhaven Dungeon (fire giants, greater demons) needs its entry fee
and an axe; that's yours to bring.

Wilderness tasks are never fought (wilderness is banned): answer **skip** or **mine**.
