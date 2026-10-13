# F2P training methods

What the bot can train on an F2P account, and what to mark for each. Pick them in the
panel (**One activity**, or in a schedule). Every gathering method can **drop** (fastest
XP) or **bank** (keep what you gather: ore, fish, logs): choose with **When full**.
Banking walks to the bank and back ([travel.md](travel.md)).

| Skill | Method | Levels | Bank |
|---|---|---|---|
| Mining | copper & tin, Varrock east mine | 1–15 | Varrock east |
| Mining | iron, Varrock east mine | 15+ | Varrock east |
| Fishing | net fishing (shrimps, anchovies), Draynor | 1–20 | Draynor |
| Fishing | fly fishing (trout, salmon), Barbarian Village | 20+ | Edgeville |
| Fishing + Cooking | fish shrimps, cook them on the fire by Draynor bank, bank | 1–20 | Draynor |
| Fishing + Cooking | fly fish, cook on the Barbarian Village fire, bank (cooking 25+) | 20+ | Edgeville |
| Woodcutting | trees Lumbridge, oaks Draynor, willows Draynor | 1 / 15 / 30+ | Draynor |
| Cooking | beef, shrimps, trout, salmon on the fire outside Draynor bank | 1 / 1 / 15 / 25+ | Draynor |
| Cooking | the same on the Lumbridge castle range (backup) | 1 / 1 / 15 / 25+ | Lumbridge (top floor) |
| Firemaking | logs, oaks, willows (then maples, yews) from the Grand Exchange | 1 / 15 / 30+ | Grand Exchange |
| Smithing | smelt bronze bars (copper + tin), Al Kharid furnace | 1–15 | Al Kharid |
| Smithing | smelt iron bars (half of them fail, as in the game), Al Kharid furnace | 15+ | Al Kharid |
| Smithing | bronze daggers, then platebodies: bronze, iron, steel, mithril, adamant, Varrock west anvils | 1 / 18 / 33 / 48 / 68 / 88 | Varrock west |
| Combat | cows, Lumbridge: kill only, or bury bones | 1–40 | — |
| Magic | Wind Strike, then Fire Strike on cows | 1 / 13–25 | — |
| Ranged | bow and arrows on cows, picking the arrows back up | 1–40 | — |
| Crafting | leather gloves, then leather bodies (then gem cutting from 20) | 1 / 14 | Grand Exchange |
| Runecraft | air runes south of Falador (Rune Mysteries) | 1–9 | Falador east |

Willows wait until you're combat 41 (dark wizards next to them).

## What to mark

- **Mining**: Object Markers on the rocks you want, color `rock` (`#FF4000`). Only the ore you're mining: mark copper and tin rocks for copper &
  tin, iron rocks for iron. A pickaxe anywhere in the inventory (or wielded), untagged.
  Gems found while mining are dropped or banked with the ore.
- **Fishing**: NPC Indicators on "Fishing spot" in `fishing_spot`. Net for shrimps; rod and
  feathers for fly fishing (both untagged: they're never dropped or banked).
- **Cooking**: Object Markers on the fire outside Draynor bank, the fire in Barbarian
  Village (for fish + cook) and/or the Lumbridge castle range, all in `range`. Bank tab `cooking` with raw
  beef, raw shrimps, raw trout, raw salmon in bank slots 5–8 (counting from 1).
- **Firemaking**: a tinderbox in the first inventory slot; bank tab `firemaking` with
  willow logs first and logs, oak logs in slots 4 and 5; the `fm_start` Ground Marker
  where the line starts.
- **Smithing**: Object Markers on the Al Kharid furnace in `furnace` and the Varrock west
  anvils in `anvil`. A hammer in the inventory (it's kept, never banked). Bank tab
  `smithing`: copper ore, tin ore, iron ore in slots 1–3, then bronze, iron, steel,
  mithril, adamantite bars in 4–8. Set the bank's **X** quantity to **14** (bronze bars
  take 14 copper + 14 tin). Steel and better bars: buy them, the bot only smelts bronze and
  iron.
  The furnace and anvil menus are taught once: in game, open the menu (use an ore on the
  furnace / a bar on an anvil), then panel → Learn → pick the button in **Teach a click** →
  hover that button in the menu → **Just Enter**. Do *Bronze bar* and *Iron bar* on the
  furnace, *dagger* and *platebody* on the anvil. In the anvil menu, also pick
  quantity **All** once; the game remembers it.
- **Magic**: runes in the inventory (they're tagged). Teach each spell once: open the magic
  tab, panel → Learn → Teach a click → *Wind Strike* / *Fire Strike*. Out of runes ends the
  activity (it never starts attacking by hand).
- **Ranged**: bow wielded, arrows in the quiver. In Ground Items, the arrows should show in
  the `loot` color; picked-up arrows are wielded again.
- **Crafting**: needle and thread in the inventory (kept), bank tab `crafting` with leather
  in slot 1. Teach *gloves* and *body* in the leather menu (use the needle on leather to
  open it).
- Items are tagged automatically by the bot's RuneLite profile (new this time: iron ore,
  salmon, burnt meat, bars, daggers, platebodies, mind runes, arrows, leather: rebuild and re-import the profile).

The marker checklist for everything is in [markers.md](markers.md).
