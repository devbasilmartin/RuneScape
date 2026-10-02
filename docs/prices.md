# Prices

Prices come from the **OSRS Wiki real-time prices API** (your server follows official
prices). Nothing here touches the in-game GE: you do all trading; the bot advises.

The Discord service polls hourly for the items that matter right now: supplies of the
methods usable at your current levels, their products, and whatever the bot has banked.
History is kept for 30 days in `data/prices/`.

## What you get on Discord

- **Sell:** something the bot banked is up ≥10% on its 7-day average and the pile is worth
  ≥500k. (Alerts start once there are 3 days of history.)
- **Buy:** a supply your upcoming training needs is down ≥10% on its 7-day average.
- Each alert at most once per item per 24 hours.
- **Method switches:** in goals mode, when the planner changes method for a skill, you're told
  why (profit per hour), e.g. after prices flip.
- **Tool upgrades:** "Woodcutting 41: rune axe unlocked", once.
- `/shopping`: what to buy for about 12 hours of training at current prices.
- `/sold ITEM`: you sold something the bot produced; it stops counting towards sell alerts.

From the VM: `python -m skillbot prices` (poll now, print alerts and the shopping list),
`python -m skillbot sold willow_logs`.

## Live profit in planning

Library methods with a `trade:` (items per hour in and out) are ranked by **live** profit
instead of their fixed estimate:

```yaml
fire_runes_alkharid:
  trade: {inputs: {rune_essence: 1700}, outputs: {fire_rune: 1700}}
```

## Settings

```yaml
prices:
  sell_rise: 0.10
  buy_drop: 0.10
  min_value: 500000
  cooldown_hours: 24
  poll_minutes: 60
  names: {burnt_fish: null}     # tag name → wiki item name, where they differ
```

Tag names map to wiki names by turning `_` into spaces (`willow_logs` → "Willow logs").
