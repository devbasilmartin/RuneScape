# Walking between places (F2P)

The bot walks between the F2P places it knows: banks, activity spots, the Lumbridge castle
stairs. That lets activities bank (**When full: bank**) and schedules move from one
activity to the next. It uses the **Shortest Path** plugin: the bot sets a target on the
world map, the plugin draws the way, the bot follows it.

The places are in `library/places/f2p.yaml`, by their world coordinates, so you don't
record them. The bot always knows which one it's at: the activity it's doing or the bank
it just used. Start a run where the activity happens, as you do now.

## Set up (once, about 10 minutes)

1. **Shortest Path**: RuneLite → the wrench (Configuration) → **Plugin Hub** at the bottom →
   search `Shortest Path` → Install. In its settings:
   - path color `#FF0080`, fully opaque
   - draw the path **on the minimap** and **in the world** (tiles)
   - **avoid the Wilderness** on
   - cancel/clear the target **when you arrive**
2. **Lumbridge castle stairs** (for Lumbridge bank, on the top floor): with Object Markers,
   shift + right-click the south staircase → **Mark object**, on the ground floor, the
   first floor and the top floor. Set the marker color to `#C000C0` (`stairs`).
3. **Measure the map** (in Lumbridge, anywhere):
   1. Panel → Setup → **Calibrate map**. The world map opens.
   2. Output asks you to hover **lumbridge spawn**: put the mouse in the middle of the
      castle courtyard on the map, click **Just Enter**.
   3. Then **lumbridge cows**: the middle of the cow field across the river, north-east of
      the castle. **Just Enter**.
   4. The bot drags the map a little and back by itself: that's it measuring which part
      of the window is map (where it can click and drag). Hands off for 2 seconds.
   5. It says `the map's area: ...` and `saved: N pixels per tile`. **Don't zoom the world
      map from now on**: the measurement is for this zoom. (Already calibrated? Run it again
      once to get the map's area too.)

## Try it

Stand at the cows, then in a terminal:

```sh
python -m skillbot travel "lumbridge bank" --from "lumbridge cows" --until bank
python -m skillbot travel "lumbridge cows" --from "lumbridge bank"
```

The first should walk to the castle, climb to the top floor and stop with the bank booth
in sight; the second climbs down and walks back.

## Places

Lumbridge (spawn, bank, cows, trees, swamp mine), Draynor (bank, willows, fishing, oaks),
Port Sarim, Falador (east and west bank), Barbarian Village (and its fishing), Edgeville
bank, Varrock (west and east bank, west and east mine, earth ruins), the Grand Exchange,
Al Kharid (bank, mine, fire ruins: carry 10 coins for the toll gate).

The coordinates come from the game's map; the bot only needs to get close (it stops when
the activity's highlight is on screen). If it walks somewhere odd, record a video and send
me the frames.

## When something goes wrong

- *"the world map's scale isn't measured"*: do step 3.
- *"no Shortest Path route drawn"*: the plugin isn't on, or its path color isn't `#FF0080`.
- *"stuck while walking"*: a closed door or a gate on the way. Tell me where.
- *"can't see stairs"*: mark the staircase on that floor (step 2).
- *"walked to X but ... isn't in sight"*: it arrived but the highlight (bank booth, trees)
  isn't marked there, or the place's tile is off.
