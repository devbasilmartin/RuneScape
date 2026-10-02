# Minigames and routines (Phase 3)

Phase 3 activities are **routines**: YAML in `library/minigames.yaml` instead of code, because
they depend on details only the real client shows. When something doesn't match (a menu
row, a timeout, an extra click), fix the routine; no programming needed. The language is
documented at the top of `skillbot/routine_spec.py`; quick reference:

```yaml
- name: mine paydirt
  when: {visible: ore_vein}          # skip unless...
  repeat_until: {full: true}         # repeat until...
  until_fail: true                   # ...or until a wait_for times out
  max: 60
  count: loads                       # counters for when: {counter_at_least: {loads: 3}}
  exhausted_if: {lacks: rune_essence}
  do:
    - click: ore_vein                # highlight (registry name), {item: name} or {point: [x, y]}
    - wait_for: {gained: paydirt}
      timeout: 30
```

Actions: `click` (with `right_option: N` for a right-click menu row), `use: {item, target}`,
`key`, `type` (`{name}` filled from the step's `vars`), `wait`, `wait_for`, `bank`, `drop`,
`travel` / `walk` (with `until: color`), `cast: {spell, on_item}`, `dialog: [options]`,
`tab`, `notify`, `progress`. Conditions: `visible`, `not_visible`, `near`, `has`, `lacks`,
`count_at_least`, `full`, `hp_below`, `counter_at_least`, `gained`, `lost`, `any`.
Don't write a bare `on:` key: YAML reads it as `true` (the loader tells you).

Each minigame's colors live in its own **area** in `colors.yaml`, so they can reuse colors
used elsewhere; `python -m skillbot setup STEP` lists what to mark.

## The routines and what to check first

| Method | Mark | Check on the first supervised run |
|---|---|---|
| Motherlode Mine | ore veins, hopper, sack, **broken** strut (Object Markers on the broken one only); tag every ore + nuggets `mlm_ore` | sack timing (every 3 loads), bank chest |
| Blast Furnace gold | conveyor, bar dispenser | the coffer and foreman fee are yours to top up; dispenser "take" key |
| Wintertodt | bruma roots, lit / broken / unlit brazier (each state its own marker) | game start/end waiting, the reward cart (you collect for now) |
| Fishing Trawler | gangplank, your spam spot, reward net | the spam spot itself, collecting the reward |
| Red chinchompas | Hunter plugin trap colors, Ground Items on dropped traps, trap tiles | right-click rows for Reset / Lay |
| Ensouled heads | the reanimated monster as `enemy` | spell position `reanimate_adept` (or the tier you use) |
| Gilded altar (public host) | Phials, Rimmington portal, the altar, the house exit | `vars: {host: NAME}`, Phials' and the portal's dialog options |
| Arceuus blood runes | runestones, Dark Altar, blood altar | travel destinations, chiselling key |
| Tithe Farm | Tithe Farm plugin / markers per plant state | the most uncertain: plant states and watering |

## Quests

`python -m skillbot quest "Rune Mysteries"` follows **Quest Helper** (Plugin Hub). Set its
highlight colors to the registry's `quest_target`, `quest_dialog` and `quest_item`. It
continues dialogs, clicks the highlighted chat option, uses highlighted items on highlighted
targets, and clicks highlighted NPCs/objects. With nothing highlighted for 30 seconds it stops
and tells you: a step it can't do, or the quest is done (`quest-done "Rune Mysteries"`). Get the
quest's items first. Always run it while watching.
