# First run: from a calibrated VM to the bot chopping trees

Where you are: the VM is set up, the client runs, `calibrate` finds the game.
Each step says what to type and what you should see. Paste anything else to Claude.

Open a terminal in the VM (it starts in `~/skillbot` with the environment on).

## 1. Get the latest version

```sh
git pull
```

## 2. RuneLite settings (once)

In RuneLite (the wrench icon at the top of the right sidebar → Configuration):

- **GPU** plugin: **off**.
- **Inventory Tags**, **Object Markers**, **NPC Indicators**, **Ground Items**,
  **Ground Markers**: **on** (the profile in step 3 also turns them on).
- **Stretched Mode**: **off**.

In the game (the game's own settings, the wrench in the bottom-right tab bar):

- **Display → Game client layout: Fixed - Classic layout** (it is already).
- **Controls → Shift click to drop items: on** (the bot drops logs with shift-click).
- Zoom the camera all the way out (scroll wheel) and point it north (click the compass).

Don't resize or move the RuneLite window after calibrating; if you do, run
`python -m skillbot calibrate` again.

## 3. Load the bot's highlight profile

The colors changed, so build it again even if you imported one before:

```sh
python -m skillbot runelite-profile
```

In RuneLite: wrench → **Profiles** (the icon with two people at the top of the
configuration panel) → **Import Profile** → pick `~/skillbot/bot-profile.properties`.
Select the new profile so it's active; rename it `bot` (delete older imports).

You should see: your logs get a colored outline in the inventory.

```sh
python -m skillbot debug
```

You should see: `tagged slots: {1: 'logs', 2: 'logs', ...}` (the axe stays untagged:
untagged items are tools and are never dropped).

## 4. Levels

Open the **skills tab** in game (the bar-chart icon), then:

```sh
python -m skillbot learn-digits       # type the levels you see when it asks
python -m skillbot levels             # should print your real levels
```

## 5. Run energy

```sh
python -m skillbot calibrate-run      # it asks you to turn run on, then off
python -m skillbot learn-energy       # type the energy number once, then walk around
```

## 6. Mark some trees

Go to a spot with normal trees (Lumbridge or Draynor). For each tree nearby:
**shift + right-click the tree → Mark object**. Then set the marker color to the bot's
tree color: shift + right-click a marked tree → **Color** → `#40C0FF`
(or: wrench → Profiles → Export, then `python -m skillbot runelite-profile --from
<the export>` and import the result: it colors every marked tree for you).

```sh
python -m skillbot debug
```

You should see: a green box labelled `normal trees` around each tree in `debug.png`.

## 7. The first real run

You watch; the bot chops and drops logs. Make your config if you haven't:

```sh
ls config.yaml || cp config.example.yaml config.yaml
python -m skillbot run --supervised
```

It runs the first step in `config.yaml` (`normal trees`: chop, drop when full, until
woodcutting 15). Stop it any time by moving the mouse into a screen corner, or Ctrl+C in
the terminal.

Send Claude: the terminal output, and a `debug.png` if something looked wrong.
