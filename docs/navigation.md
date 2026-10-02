# Navigation

The bot travels like you would: **teleport to a hub, set a Shortest Path target on the
world map, follow the drawn path**. A step with `location: NAME` travels there whenever its
target isn't in sight (at start, after a death, after you played).

## 1. Plugins

- **Shortest Path** (Plugin Hub). Settings:
  - path color = the registry's `path` (`#FF0080`), drawn **in the game world and on the minimap**
  - **avoid the Wilderness** on
  - clear the target when you arrive (so a finished path disappears)
- **Ground Markers**: mark the tile each teleport lands on with `hub_marker` (`#C0C000`), so the
  bot can tell the teleport worked.

## 2. Hubs

In `config.yaml`:

```yaml
hubs:
  varrock:
    teleport: {item: varrock_teleport}          # a tablet: tag it in Inventory Tags
    marker: hub_marker
  edgeville:
    teleport: {item: amulet_of_glory, option: 1} # rub, then press the option's number
    marker: hub_marker
  lumbridge:
    teleport: {spell: [566, 222]}                # position of the spell in the magic tab
    wait: 12                                     # home teleport takes a while
    marker: hub_marker
```

Teleport items are Inventory Tags items like any other (add them to `items:` and keep them
with `keep:` on steps that bank). When they run out you get the usual out-of-stock message.

## 3. Destinations

For each place you want to go, record where it is on the world map, as seen from a hub:

```sh
python -m skillbot add-destination "varrock trees" --hub varrock
```

The bot teleports to the hub and opens the world map; hover the place on the map and press
Enter. **Don't scroll or zoom the map** while doing this, and leave the map's zoom where it is
afterwards: every destination depends on it. Stored per account in `data/destinations.json`.

Then give steps a location:

```yaml
  - name: yews
    location: "woodcutting guild yews"
    ...
```

Try a trip any time: `python -m skillbot travel "varrock trees" --until tree`.

## 4. First-run checks (please report back)

These are assumptions the design rests on; the first real trip shows whether they hold:

1. **The world map opens centred on the player** every time. If it doesn't, offsets drift and
   targets land in the wrong place.
2. **Which right-click option is "Set target"** on the world map: set `map_menu_option`
   (1 = the first option under the menu header). Right-click the map once by hand to see.
3. Layout positions to confirm with `debug`: `world_map_button`, `world_map_center`,
   `minimap_center`, `chatbox`.

If the path stops at a door or gate, the bot reports "stuck while walking"; send me a
screenshot and we'll handle that obstacle.
