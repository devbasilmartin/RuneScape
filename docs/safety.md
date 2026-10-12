# Safety: low HP, random events, deaths, crowded worlds

These run during every step. Set the colors in RuneLite (they're in `colors.yaml`) and the
options below in `config.yaml`.

```yaml
danger_color: random_event       # NPC Indicators: all random-event NPCs (never clicked)
genie_color: genie               # NPC Indicators: "Genie" (talked to, lamp used)
respawn_color: respawn           # Ground Marker: the tile you respawn on
grave_color: grave               # NPC Indicators: "Grave"
other_player_color: other_player # Player Indicators: "Highlight others"
safety:
  genie_skill_point: [600, 300]  # your chosen skill in the lamp window (find it with debug)
  lamp_confirm: [640, 420]       # the lamp window's confirm button
  grave_take: [300, 300]         # the grave window's "take all"
  hop: true
  hop_crowd: 3                   # this many other players near the target...
  hop_minutes: 2                 # ...for this long → hop
  hop_cooldown_minutes: 5
  hop_hotkey: [ctrl, shift, right]   # World Hopper's "next world" hotkey
```

## Low HP (every activity)

Whatever the bot is doing (chopping, fishing, fighting, walking), it looks at your HP
every couple of seconds, on the Status Bars plugin's health bar left of the inventory (the
bot's RuneLite profile turns it on).

When HP is **below half** (or the activity's own `eat_below`):

1. **Food in the inventory: it eats.** The activity's food list if it has one, otherwise
   any tagged food it knows: cooked meat, shrimps, anchovies, trout, lobster, swordfish.
   Tag food in Inventory Tags in its color (the bot's RuneLite profile has them;
   `skillbot colors` lists them).
2. **No food, and something is hitting you** (HP went down in the last minute) or HP is
   **below 20%**: it gets away (walks to the bank if the activity has a bank route),
   **logs out**, and stops. The stop message (Discord, the panel's Output) says so.
3. **No food, but HP is steady** (e.g. you start woodcutting right after a fight): it
   carries on. Nothing is hitting you, and HP comes back by itself.

Fighting activities that bank for more food (`when_out_of_food: bank`) go and get it
themselves; the guard only steps in for them below 20%.

**Dangerous activities:** each escape is written to `data/danger.json`. After **2 escapes
within two weeks** on the same activity, it's skipped (with a message) until that skill
is past the highest level it happened at. Delete the activity's entry from the file to
allow it again sooner.

It doesn't eat while dropping items (shift is held) or in the bank.

## Random events

Add every random-event NPC to NPC Indicators in the `random_event` color (`skillbot setup`
lists the common names). The bot never clicks a point inside one: if one stands on its
target it uses another target or waits. The **Genie** gets its own color instead: the bot
talks to it, uses the lamp (tag it `lamp` in Inventory Tags) on the skill at
`genie_skill_point`, and confirms. Without those positions it just tells you about the lamp.

## Deaths

Mark your respawn tile (Lumbridge, or wherever you've set it) with the `respawn` Ground
Marker. When the bot sees it, it tells you, travels back to the step's `location`, clicks
the grave and takes everything, then wears the step's `gear` again (tag those items).
A second death on the same step within an hour stops the bot: that step is too dangerous
as set up. Steps without a `location` stop at the first death, since the bot can't get back.

The Wilderness is avoided by Shortest Path's setting (see [navigation.md](navigation.md)).

## Crowded worlds

Turn on Player Indicators' "highlight others" in the `other_player` color, and in World
Hopper set the "next world" hotkey and limit hopping to your favourite low-population
members worlds. When 3+ other players are near your target for 2 minutes, the bot hops,
only between inventories, at most every 5 minutes, and after 5 hops in a row it stays put
(probably just a busy time of day).

**To verify on the real client:** the lamp and grave window positions, and that World
Hopper's hotkey only cycles through the worlds you want.
