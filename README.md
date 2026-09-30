# fishbot

Screen-reading fishing/cooking bot for a fixed-mode RuneLite client pointed at a private
server that allows automation. It relies on RuneLite highlight plugins, so detection is
just "find this exact color", which is far more reliable than recognizing game graphics.

First target: **net fishing at Draynor Village** (shrimps/anchovies), banking at Draynor bank.

## Install

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

On Linux, pyautogui needs X11 (not Wayland). On macOS, grant your terminal Screen Recording
and Accessibility permissions. Multiple monitors work: capture uses absolute screen coordinates.

## RuneLite setup

Everything the bot sees comes from RuneLite highlights, so there are no images to capture.
Use the exact colors from `config.yaml` (defaults below), fully opaque.

| Plugin | What to mark | Default color |
|---|---|---|
| NPC Indicators | add `Fishing spot` to "NPCs to highlight" (outline or hull; turn names off) | cyan `#00FFFF` |
| Object Markers | shift + right-click the Draynor bank booth → Mark object | magenta `#FF00FF` |
| Object Markers | a range, or the fire you cook on | yellow `#FFFF00` |
| Inventory Tags | shift + right-click each item → Tag (outline style) | one color per item, see `items:` |
| Ground Markers | shift + right-click a tile → Mark tile; one halfway tile each way | `routes:` colors |

With Inventory Tags, tag raw shrimps, raw anchovies, the cooked fish and the burnt fish. Leave
your net untagged: the bot ignores untagged items and never drops or banks them.
Pick highlight colors that don't appear on the game map, the interface or item sprites.

In game: run RuneLite in **fixed mode** (Settings → Display → *Fixed - Classic layout*), zoom the
camera **all the way out**, enable **Shift-click drop** and **Esc closes the current interface**,
and set the bank quantity to **All**.

Draynor has no range. For the cook modes, either light a fire and mark it, or run the bot at the
Lumbridge castle range and mark tiles for the `to_cook` / `to_bank` routes.

## Calibrate

```sh
python -m fishbot calibrate   # hover the top-left pixel of the game canvas, press Enter
python -m fishbot debug       # writes debug.png
```

Open `debug.png`. The grey boxes should sit on the inventory slots, tagged items should show up
red with their names, and green boxes should surround every highlighted spot, booth and tile.
If the slot grid is off, adjust `layout:` in `config.yaml`. The default fixed-mode offsets are
still unconfirmed, so check them before running.

## Run

```sh
python -m fishbot run
```

**Move the mouse into any screen corner to stop immediately.** The bot also stops after
`max_runtime_minutes` and when it hits a situation it can't handle (it logs why).

Modes (`mode:` in config):

| mode        | when the inventory is full                 |
|-------------|--------------------------------------------|
| `drop`      | shift-click drop all fish                  |
| `bank`      | click the bank booth, deposit fish, go back|
| `cook_drop` | cook on the marked range/fire, then drop   |
| `cook_bank` | cook, then bank                            |

## How it works

- `layout.py`: fixed-mode positions of the viewport, inventory slots and compass.
- `vision.py`: color masks → dilated connected components → blob boxes.
- `inventory.py`: reads which Inventory Tags color is drawn in each slot.
- `bot.py`: the loop. While fishing, it waits as long as fish keep arriving and a spot is next
  to the player; otherwise it clicks the nearest highlighted spot. Ground Marker `routes` are a
  fallback when a target isn't on screen. It stops if several spot clicks in a row catch nothing
  it can see (usually an untagged fish).

## Tests

```sh
pip install pytest && python -m pytest
```

Tests use synthetic screenshots and a fake game, so they don't need a display.
