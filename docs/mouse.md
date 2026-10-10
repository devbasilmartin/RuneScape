# Mouse-style A/B testing

Which way of moving and aiming lands clicks on odd-shaped highlights? Off by default. The normal
click path is unchanged until you switch this on.

## Why

The bot used to click a point near the middle of a highlight's **bounding box**. For an
L-shaped, bent or hollow model, that point is often not on the model at all. In simulation, aiming
at the box centre of an L shape or a ring hit 33% of the time, while aiming at the point deepest
inside the outline hit 100%.

Every highlight the bot finds now carries its **outline** (`Blob.polygon`):
- An outline-style highlight (NPC Indicators, Object Markers) counts as the filled silhouette it
  traces. Small gaps from things standing in front of it are closed.
- A filled highlight keeps its exact shape, holes included.

The [humanized_input](https://github.com/devbasilmartin/Humanized-input) library then plans each
click into that outline. The bot compares styles by what actually happened in the game.

## Turning it on

```sh
pip install "git+https://github.com/devbasilmartin/Humanized-input@ccr-cf7d2098-mwb8ib"
cp mouse_styles.example.yaml mouse_styles.yaml
```

```yaml
# config.yaml
mouse:
  enabled: true
  styles: mouse_styles.yaml        # next to config.yaml
  pick: round-robin                # or random
  log: mouse_outcomes.jsonl        # in the data folder, kept across sessions
```

Each click on a highlight uses the next style in turn. A style combines:
- `path`: `human`, `linear` or `instant`
- `aim`: `human`, `center` (box centre), `centroid`, `deepest` or `uniform`
- `speed`
- `aim_jitter_px`
- any of the library's `pointer_*` settings

The library's documentation has the full list. Clicks on fixed screen points (tabs, inventory
slots, the bank) are unchanged.

If a planned click would land on a random-event NPC, it isn't made, and that click uses the usual
danger-aware point instead.

## What counts as a hit

Each click is judged by the check its step already makes:

| Step | Hit when |
|---|---|
| gather (trees, rocks, fishing...) | an item arrives; a re-click with nothing gained is a miss |
| combat | the clicked enemy gets a health bar (a fight started); an attack that never starts one is a miss |
| combat loot | the inventory grows within 6 seconds |
| agility | the obstacle is crossed |

Clicks without such a check (route tiles, the bank booth, marks of grace, thieving, routines,
quests) still use the styles, but their outcomes aren't logged.

## Results

```sh
python -m skillbot mouse-summary          # per style, overall and per step
python -m skillbot mouse-summary --json
```
```
(all):
  deepest        212/220    96.4%  0.18s
  box-centre     141/219    64.4%  0.21s
willows:
  ...
```

The log is `data/mouse_outcomes.jsonl`, one line per click, so it's easy to analyse further.
