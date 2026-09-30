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

1. **Fixed mode** (Settings → Display → Game client layout: *Fixed - Classic layout*). Don't resize it.
2. **NPC Indicators**: add `Fishing spot` to "NPCs to highlight". Set the highlight style to *Outline*
   or *Hull*, the color to exactly the value in config (default cyan `#00FFFF`),
   and turn off names/minimap drawing so text doesn't pollute the color.
3. **Object Markers**: shift + right-click the Draynor bank booth → *Mark object*, and set the marker
   color to magenta `#FF00FF`. For cooking, mark a range (or fire) in yellow `#FFFF00`.
4. In game: zoom the camera **all the way out**, enable **Shift-click drop**, enable
   **Esc closes the current interface**, and in the bank set the quantity to **All**.

Draynor has no range. For the cook modes, either light a fire and mark it, or run the bot at
the Lumbridge castle range (set `to_cook` / `to_bank` routes accordingly).

## Calibrate

```sh
python -m fishbot calibrate          # hover top-left of the game canvas, then baseline with only your net
python -m fishbot calibrate --bank   # optional: baseline while the bank is open
python -m fishbot debug              # writes debug.png
```

Open `debug.png`: grey boxes should sit exactly on the inventory slots, orange marks tool slots,
red marks new items, and green boxes should surround each highlighted spot/booth. If the slot grid
is off, adjust `layout:` in `config.yaml`. These default fixed-mode offsets are still unconfirmed,
so check them against your client before running.

For the cook modes, capture templates while those items are in your inventory:

```sh
python -m fishbot capture-item raw_shrimps 1      # slot index 0-27
python -m fishbot capture-item raw_anchovies 2
```

Optionally capture part of the bank window so the bot can confirm the bank opened
(pick coordinates from a `debug.png` taken with the bank open):

```sh
python -m fishbot capture-region bank_open X Y W H
```

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

- `layout.py`: fixed-mode positions of the viewport, inventory slots, minimap and compass.
- `vision.py`: color masks → dilated connected components → blob boxes; template matching.
- `inventory.py`: a slot is "new" when it differs from the calibrated baseline, so tools are
  ignored. Templates identify items for cooking.
- `bot.py`: the loop. While fishing, it waits as long as fish keep arriving and a spot is next
  to the player; otherwise it clicks the nearest highlighted spot. Minimap `routes` are a fallback
  when a target isn't on screen.

## Tests

```sh
pip install pytest && python -m pytest
```

Tests use synthetic screenshots and a fake game, so they don't need a display.
