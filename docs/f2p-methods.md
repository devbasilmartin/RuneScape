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
| Woodcutting | trees Lumbridge, oaks Draynor, willows Draynor | 1 / 15 / 30+ | Draynor |
| Cooking | beef, shrimps, trout, salmon on the Lumbridge castle range | 1 / 1 / 15 / 25+ | Lumbridge (top floor) |
| Firemaking | logs, oaks, willows (then maples, yews) from the Grand Exchange | 1 / 15 / 30+ | Grand Exchange |
| Combat | cows, Lumbridge | 1–40 | Lumbridge |

Willows wait until you're combat 41 (dark wizards next to them).

## What to mark

- **Mining**: Object Markers on the rocks you want, color `rock` (`#FF4000`). Only the ore you're mining: mark copper and tin rocks for copper &
  tin, iron rocks for iron. A pickaxe anywhere in the inventory (or wielded), untagged.
  Gems found while mining are dropped or banked with the ore.
- **Fishing**: NPC Indicators on "Fishing spot" in `fishing_spot`. Net for shrimps; rod and
  feathers for fly fishing (both untagged: they're never dropped or banked).
- **Cooking**: Object Markers on the castle range in `range`. Bank tab `cooking` with raw
  beef, raw shrimps, raw trout, raw salmon in bank slots 5–8 (counting from 1).
- **Firemaking**: a tinderbox in the first inventory slot; bank tab `firemaking` with
  willow logs first and logs, oak logs in slots 4 and 5; the `fm_start` Ground Marker
  where the line starts.
- Items are tagged automatically by the bot's RuneLite profile (new this time: iron ore,
  salmon, burnt meat: rebuild and re-import the profile).

The marker checklist for everything is in [markers.md](markers.md).
