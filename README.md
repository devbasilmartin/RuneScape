# skillbot

Screen-reading skilling bot for a fixed-mode RuneLite client pointed at a private
server that allows automation. Everything it sees comes from RuneLite highlights
(exact colors), and it works through a plan of training steps, switching methods as
levels go up.

It covers the gathering and processing skills (Woodcutting, Mining, Fishing, Firemaking,
Cooking, Smithing and Crafting: anything that is "use item on station, pick from a menu")
and combat (Attack, Strength, Defence, Hitpoints, Ranged, Magic, and Prayer from burying
bones). Runecrafting comes next.

## Install

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

On Linux, pyautogui needs X11 (not Wayland). On macOS, grant your terminal Screen Recording
and Accessibility permissions. Multiple monitors work: capture uses absolute screen coordinates.

## RuneLite setup

Use the exact colors from `config.yaml`, fully opaque, and keep them well apart.

| Plugin | What to mark | Config key |
|---|---|---|
| Object Markers | trees, rocks, furnace, anvil, range, bank booths (shift + right-click → Mark object) | step `target`, `bank_color` |
| NPC Indicators | `Fishing spot`, or the monsters to fight (outline or hull, names off) | step `target` |
| Ground Items | loot to pick up, with **Highlight tiles** on, in one color | combat `loot` |
| Status Bars | on, showing Hitpoints on the left of the inventory | `hp_bar_color`, `layout.hp_bar` |
| Inventory Tags | every item the bot gathers, uses or makes (shift + right-click → Tag) | `items:` |
| Ground Markers | route tiles, and the first tile of a firemaking lane | `routes:`, firemaking `target` |
| Key Remapping | on, so pressing space for dialogs doesn't type into chat | |

Object Markers highlight one object on one tile, so a tree or rock loses its highlight when
it's depleted. The bot uses this to move on to the next one. Leave tools (axe, pickaxe, net,
tinderbox, hammer) **untagged**: the bot ignores untagged items and never drops or banks them.

In game: run RuneLite in **fixed mode** (Settings → Display → *Fixed - Classic layout*), zoom the
camera **all the way out**, enable **Shift-click drop** and **Esc closes the current interface**,
and set the bank's withdraw/deposit quantity to what your steps expect (All, or X = 14 for smelting).

## Calibrate

Log in first, then:

```sh
python -m skillbot calibrate          # hover the top-left pixel of the game canvas, press Enter
python -m skillbot debug              # writes debug.png
```

`calibrate` also records what the logged-in screen looks like (a few color samples, used to
detect logouts). Open `debug.png`: the grey boxes should sit on the inventory slots, tagged
items should be labeled in red, and green boxes should surround every highlight. If anything is
off, adjust `layout:` in `config.yaml`. The default fixed-mode offsets are still unconfirmed.

### Levels

The bot reads levels from the skills tab by learning the shapes of the digits:

```sh
# open the skills tab first
python -m skillbot debug --skills     # yellow boxes must cover each skill's base level
python -m skillbot learn-digits       # type in the levels you see
python -m skillbot levels             # prints what it can read
```

Digits you don't have yet are learned as you level: until all ten are known, the bot checks
the skills tab after every item so each level-up is exactly +1. The shapes are stored as text
in `data/digits.json`; delete it and re-run `learn-digits` if a level ever reads wrong.

### Bank slots

Steps that restock click fixed bank slots. With the bank open, `python -m skillbot debug --bank`
numbers the bank grid; put each input in the slot its step's `withdraw:` names.

## The plan

`plan:` in `config.yaml` is a list of steps, worked top to bottom. See `config.example.yaml`
for a Draynor woodcutting/fishing/firemaking plan plus mining, smelting, smithing and cooking
examples.

| task | what it does | typical skills |
|---|---|---|
| `gather` | click the nearest `target` until full, then `drop` or `bank`; optional inline `process` (e.g. cook each load on a fire) | Woodcutting, Mining, Fishing |
| `process` | withdraw inputs, (optionally `use_item` on) the `target` station, send `confirm` keys/clicks, wait until the inputs are used up | Cooking, Smelting, Smithing, Crafting |
| `firemaking` | stand on the `target` tile, light every log with the tinderbox in `tool_slot` | Firemaking |
| `combat` | attack the nearest free `target`, eat `food` below `eat_below` HP, pick up `loot`, bury `bury` | Attack, Strength, Defence, Hitpoints, Ranged, Magic, Prayer |

### Combat

- It never attacks an NPC that already shows the game's green/red health bar (someone else's
  fight), and it treats a target as dead when its highlight disappears.
- `style` (0-3) picks the attack style button in the Combat Options tab when the step starts:
  alternate Attack/Strength/Defence steps with `max_minutes` to train them together. Hitpoints
  rises on its own. A step can also name `hitpoints` or `prayer` as its skill.
- Magic: set `cast` to the spell's position in the magic tab (find it with `debug`), or
  autocast from a staff and leave `cast` out.
- HP is the fill of the Status Bars health bar, so no numbers are read. Check it with `debug`,
  which prints the HP it sees. When food runs out it banks for more (`withdraw`), or ends the
  step with `when_out_of_food: stop`.
- Keep enemy and loot colors away from pure green and red, which the game uses for health bars;
  the config check rejects colors that are too close.
- If your character dies, the respawn point has no highlights, so after a few failed recoveries
  the bot stops rather than wandering.

A step is skipped once `skill` reaches `until_level`. With `max_minutes` it hands over to the
next step after that long, so you can alternate e.g. mining and smelting. A process step ends
early when the bank runs out of its inputs. After the last step the plan starts again from the
top, and the bot stops once every step is done or none can make progress.

Each step's `walk:` names routes to use when its bank, target or start isn't on screen. Routes
are chains of Ground Marker tiles, so they work for walks within one area. Moving between
distant areas (e.g. Draynor → Varrock) isn't supported well yet: order the plan so each area's
steps run together, and move the character yourself between areas.

## Running unattended

```sh
export SKILLBOT_USERNAME=... SKILLBOT_PASSWORD=...   # only needed for on_logout: relogin
python -m skillbot run
```

- **Move the mouse into any screen corner to stop immediately.**
- `on_logout: stop` stops when it sees the login screen; `relogin` logs back in (retrying with
  backoff up to 15 minutes, for server restarts). Credentials are read only from the environment.
  The login button positions are unconfirmed; check them the first time.
- On an error (a missing highlight, a stalled action) it closes interfaces, checks it's still
  logged in and retries. After `max_consecutive_errors` failures in a row it stops.
- Logs go to the console and `data/skillbot.log` (rotated). Levels are saved to
  `data/progress.json`.

## Code layout

- `layout.py`: fixed-mode positions (viewport, inventory, tabs, skills tab, bank grid, login).
- `vision.py`: color masks → dilated connected components → blob boxes.
- `inventory.py`: which Inventory Tags color is drawn in each slot.
- `skills.py`: digit segmentation and learning for the skills tab.
- `game.py`: shared actions: clicking highlights, walking routes, banking, dropping, tabs.
- `tasks.py`: `GatherTask`, `ProcessTask`, `FiremakingTask`.
- `combat.py`: `CombatTask`.
- `planner.py`: step selection, level refresh, error recovery.
- `session.py`: logout detection and re-login.

## Tests

```sh
pip install pytest && python -m pytest
```

Tests drive the tasks against a simulated game (trees that deplete, a bank, a range whose
cooking is interrupted by a level-up, cows that fight back and drop loot, a login screen), so
they don't need a display.
