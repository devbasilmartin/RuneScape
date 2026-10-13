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
| Combat | Al-Kharid warriors in the palace (bring food) | 20–40 | Al Kharid |
| Combat | hill giants through the brass key door (bring food; big bones banked) | 40+ | Edgeville |
| Prayer | bury bones or big bones from the bank | 1+ | Draynor |
| Mining (supplies) | rune essence through Aubury in Varrock (Rune Mysteries) | any | Varrock east |
| Crafting (supplies) | tan cowhides into leather at Ellis, Al Kharid (1 coin each, no XP) | any | Al Kharid |
| Magic | Wind Strike, then Fire Strike on cows | 1 / 13–25 | — |
| Ranged | bow and arrows on cows, picking the arrows back up | 1–40 | — |
| Crafting | leather gloves, then leather bodies | 1 / 14 | Grand Exchange |
| Crafting | gold rings, then gold amulets (u), Al Kharid furnace | 5 / 8–20 | Al Kharid |
| Crafting | gem cutting: sapphires, emeralds, rubies, diamonds | 20 / 27 / 34 / 43+ | Grand Exchange |
| Runecraft | air runes south of Falador, earth runes by Varrock, fire runes by Al Kharid (Rune Mysteries) | 1 / 9 / 14+ | Falador east / Varrock east / Al Kharid |

## Every skill in one schedule

The panel's schedules come with **f2p all skills**: every F2P skill, 30–45 minutes each,
round and round. Each line is **auto**: the best method for that skill at your level right
now, so it moves from trees to oaks to willows, cows to warriors to hill giants, by itself.
When the best one can't run (out of supplies, not proven yet when you're away), it tries
the next best. Gathering banks, so the logs, fish and ore feed firemaking, cooking and
smithing that come after it. Skills at 99 are skipped. You can add **auto** lines to your own
schedules too (the first choice under each skill in the activity list).

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
- **Al-Kharid warriors**: NPC Indicators on "Al-Kharid warrior" in `enemy`; food in bank tab
  `food` slot 1 (it fetches more when it runs out).
- **Rune essence**: NPC Indicators on Aubury in `aubury` and on the mine's Portal in
  `essence_portal`; Object Markers on the essence rock (inside the mine) in `essence_rock`.
  It right-clicks Aubury and picks **Teleport**. Teach his menu once (see *Right-click
  menus* below), or it guesses the 3rd row.
- **Tanning**: NPC Indicators on Ellis in `tanner`; coins in the inventory; cowhides in bank
  tab `crafting` slot 2. It right-clicks Ellis → **Trade**, then right-clicks the soft
  leather → **Tan All**. Teach the soft leather button once: open his menu, panel → Learn
  → Teach a click → *tanning: soft leather*. Teach both menus too (below).
- **Hill giants**: a brass key in the inventory (untagged); Object Markers on the door of the
  little house west of the Cooks' Guild in `door` (`#C00000`), and on the ladder inside and
  the one at the bottom in `stairs`; NPC Indicators on "Hill Giant" in `enemy`; food in bank
  tab `food` slot 1. Big bones are banked for Prayer.
- **Prayer**: bank tab `prayer` with bones in slot 1 and big bones in slot 2.
- **Gold jewellery**: Object Markers on the Al Kharid furnace (`furnace`); a ring mould or
  amulet mould in the inventory (tagged, kept); gold bars in bank tab `crafting` slot 3.
  Teach *jewellery menu: gold ring* and *gold amulet* (use a gold bar on the furnace to open
  it).

## Right-click menus

Wherever the bot picks from a right-click menu (Aubury's Teleport, Ellis's Trade, Tan All,
the world map's Set target), it reads the option's text, so a menu that's different on
your client doesn't make it click the wrong row. It learns each word once:

1. In the panel, Learn: type the menu's rows top to bottom in the box next to **Teach a
   menu**, as the game shows them, e.g. `Talk-to,Trade,Teleport`. You can stop before
   Walk here / Examine / Cancel.
2. Click **Teach a menu**, then **Just Enter**, and within 5 seconds hover the thing in game
   (Aubury) and hold still. The bot right-clicks it and reads each row.
3. You should see `learned 'Talk-to'`, `learned 'Trade'`, `learned 'Teleport'`.
   `menu-check.png` shows the menu it saw.

Do Aubury (`Talk-to,Trade,Teleport`), Ellis (`Talk-to,Trade`), the soft leather in his
tanning window (`Tan 1,Tan 5,Tan 10,Tan X,Tan All`) and the world map (right-click any spot:
`Set target` and what's under it). A word it hasn't learned yet falls back to the row
number, as before. A menu without the word is closed instead of clicking something else.

## Before trying one: Check step

Panel → Check → pick the activity (every library method is in the list) → **Check step**,
standing where it runs. Beyond the markers on screen it now says what's missing: clicks
and menus not taught yet, a members method on an F2P account, places it can't travel to,
the world map not calibrated.
- Items are tagged automatically by the bot's RuneLite profile (new this time: iron ore,
  salmon, burnt meat, bars, daggers, platebodies, mind runes, arrows, leather: rebuild and re-import the profile).

The marker checklist for everything is in [markers.md](markers.md).
