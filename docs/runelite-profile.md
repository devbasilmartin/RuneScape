# The RuneLite `bot` profile, generated

Every highlight color the bot looks for is in the color registry (`colors.yaml`). RuneLite keeps
a profile's settings in one file and can import one, so most of the highlighting doesn't need
to be done by hand:

```sh
python -m skillbot runelite-profile          # writes bot-profile.properties
```

In RuneLite: **Configuration (wrench) → Profiles → Import Profile**, pick the file, switch to the
imported profile, and rename it `bot`. Ids come from the OSRS Wiki on the first run, so it needs
internet once; after that it reads them from `data/runelite_ids.json`.

## What it sets up

| Plugin | Generated |
|---|---|
| Inventory Tags | every item in the registry, in its color (by item id) |
| NPC Indicators | the NPC names in `runelite/names.yaml`, each NPC in its color by id: enemies, cows, fishing spots (net/bait, cage/harpoon and net/harpoon spots apart), Ardougne knights, random-event NPCs, Genie, graves, Slayer masters, Phials |
| Ground Items | bones, big bones, cowhide and the other listed loot in `loot`, tiles highlighted |
| Player Indicators | other players in `other_player` |
| Agility | marks of grace in `mark_of_grace`; its own obstacle boxes off (they'd clash with the obstacle colors) |

It also turns these plugins on. The command prints anything it couldn't do. A random-event NPC
whose ids it can't find is **left out** rather than drawn in the enemy color, so the bot never
attacks one by mistake.

## Object Markers and Ground Markers: mark, export, recolor

These two plugins store every marker by its exact tile, so they can't be made up front. Mark them
in game with any color, and the bot colors them:

1. In the `bot` profile, **shift + right-click → Mark object** on each bank booth, tree, rock,
   range, altar and so on that you'll use. The color doesn't matter.
2. For route tiles, **shift + right-click → Mark tile**, then **Label** it with the registry name
   (`tile_plum`, `tile_blue`, `fm_start`, `afk_spot`...).
3. **Profiles → Export** (the button on the profile), save the file, then:
   ```sh
   python -m skillbot runelite-profile --from exported.properties
   ```
4. Import the new `bot-profile.properties` and switch to it.

Objects are recolored by name (`runelite/names.yaml`: "Willow tree" → `willow_tree`, "Bank booth" →
`bank`...); tiles by their label. Everything else in your export is kept. Run it again whenever you
mark more.

## Still by hand

[markers.md](markers.md) is the per-place checklist of every marker the library needs,
and which ones are recolored for you.


The command lists these too:
- **Agility obstacles**: each course's obstacles take `obstacle_1`, `obstacle_2`... in order, and
  courses reuse names (two "Tightrope"s), so color them by hand: set Object Markers' marker
  color to `obstacle_1`'s color (`python -m skillbot colors` shows it), mark the first obstacle,
  change the color, mark the next, and so on.
- A few generic items whose item depends on what you choose: `alch_item`, `bones_for_altar`,
  `ensouled_head`, `quest_item`, `burnt_fish`, the Tithe Farm seed and fruit. Right-click → Tag.
- Objects named the same for two colors, such as "Altar" (runecrafting) vs the gilded altar,
  or "Portal" in two places. The report names them.
- Plugin Hub plugins: Quest Helper's colors, Shortest Path's path color, the Tithe Farm plugin.
- Status Bars: nothing to set. Check its health color matches `status_hp` with `check-setup`.

`python -m skillbot check-setup STEP` (standing where the step runs) shows whether everything
for that step is visible in the right color.

## If the import looks wrong

The formats come from RuneLite's source code but haven't been checked against your client yet.
After importing, check one of each: a tagged item in your inventory, a highlighted cow or
fishing spot, a recolored bank booth. If one is off, send me an exported profile with that
highlight set by hand and I'll match its format.
