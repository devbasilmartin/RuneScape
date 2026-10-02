# skillbot roadmap

The plan for taking one account to 99 in every skill on our OSRS private server, as
agreed in the design interview. Each decision lists what was chosen and why. The
phase checklist at the bottom is the build order.

## Ground rules

| # | Decision | Why |
|---|---|---|
| 1 | **Server:** standard 1× XP, members and F2P worlds (membership is free), GE exists, several worlds, random events on, an up-to-date OSRS clone with Sailing. | Method choice matters a lot at 1× XP; everything has to handle the hardest version. |
| 2 | **One normal (non-ironman) account at a time.** Several accounts are supported as **profiles** (config, plan, levels, digits, credentials per account); switching means stopping one profile and starting another. | GE access shortens the path to 99 enormously. One bot process keeps the architecture simple. |
| 10 | **Pixel detection only, using RuneLite and existing Plugin Hub plugins.** No custom plugins. | You can't build or sideload plugins. Every feature must be something a plugin can draw (highlights, bars, overlays) or the game shows itself. |
| 21, 25 | **Method priority: reliability → profit → XP.** Pick the most profitable method the bot can run unattended for days; where nothing is profitable, the cheapest-loss method, funded by the rest. | A slower method that never gets stuck beats a fast fragile one over 24/7. You want the account to keep making money. |
| 22 | **Bank everything when possible.** No power-mining or dropping where banking exists. | Your preference: the resources are worth money. |
| 28 | **Small manual steps are fine** when they buy a much better method. The bot pauses and notifies you instead of falling back to something far worse. | E.g. marking a gilded altar host's tile beats burying bones. |
| 38 | **You do all GE trading yourself.** The bot never buys or sells. It sends shopping lists and sell suggestions instead. | Safety: no misread prices, no bad offers. |

## Infrastructure

| # | Decision | Notes |
|---|---|---|
| 3–5 | **VirtualBox VM on your Windows PC**: Ubuntu Desktop 24.04, **"Ubuntu on Xorg"** session (pyautogui can't control Wayland), fixed resolution (e.g. 1280×800), auto-login, no screen lock or blanking, minimized once calibrated, 4 GB RAM / 2 cores. | The bot's mouse lives inside the VM, so you keep using your PC. The old Linux partition is left alone. |
| 6 | **Supervisor + watchdog inside the VM**: a systemd user service starts RuneLite, waits for the login screen, starts the bot, restarts either if it dies, and restarts both if the screen is frozen for N minutes. At most ~5 restarts per hour, then give up and notify. **VM autostarts with Windows** (Task Scheduler); Windows Update active hours keep reboots predictable. | On restart the bot re-reads levels and continues the plan. |
| 7, 37 | **Discord, two-way bot** (bot token in an environment variable): notify on stops, failures, deaths, 99s, finished steps and manual checkpoints; **daily summary** (XP per skill, time online, deaths, supplies used and produced). Questions such as "which Slayer task?" or "which house host?" are answered from your phone. | Level-ups go in the summary, not individual pings. |
| 14 | **Pause / resume**: `pause` (or a hotkey) finishes the current action and releases the mouse so you can play; `resume` re-syncs first (re-reads levels, checks the inventory, teleports to a hub if the location is unknown). Relogin must be off or paused while you play on another client. | You'll often switch between accounts and play yourself. |
| 36 | **Highlight management**: a central **color registry** (every color assigned once by category, collisions validated per scene); `skillbot setup <method>` prints exactly what to mark; `skillbot check-setup <method>` verifies the highlights from a screenshot before the first run. **Separate RuneLite profiles**: a "bot" profile with all the highlights and your own clean profile. The pause/resume handover reminds you to switch. | Missing or slightly wrong highlights are the most likely real-world failure. |
| 42 | **Trust levels per method**: **experimental** (only with `--supervised`; pauses at the first error) → **trial** (unattended, 2-hour slices, a report after each) → **trusted** (normal 24/7 use). Promotion: 2 clean supervised hours → trial; 24 trial hours over ≥3 days with ≤1 recovered error per 4 h and no stops → trusted. Automatic demotion after 2 stops in a day. A code change resets a method to trial. Every error saves a screenshot and log tail, which become **replay tests**. | Makes "proven" measurable. |

## Engine

| # | Decision | Notes |
|---|---|---|
| 9, 11 | **Navigation: teleport to a hub, set the Shortest Path target, follow the path.** After a teleport you're on a known tile, so the world map opens centered on a known spot and each destination is a **calibrated pixel offset** (`add-destination`). Right-click → "Set target" → close the map → follow the drawn path with the "furthest visible tile" logic. Marked-tile routes remain the fallback. | First thing to verify: the world map reliably recenters on the player when opened, at a fixed zoom. Doors, gates and stairs on the path are handled as they come up. |
| 12 | **Teleports**: tablets for the main cities plus a worn glory and a games necklace early; spells once Magic allows; POH portals once built. A teleport is "an item or spell that leads to a hub"; steps name the hubs they need and the bank keeps them stocked. | |
| 15 | **Quests: semi-automatic via Quest Helper.** The bot picks highlighted dialog options, clicks highlighted NPCs, objects and items, and travels when the target is off screen. Each supported quest has an item list in config (bought by you). Puzzles, bosses and anything unhighlighted mean pause and notify. Starts with the unlock quests. | Quest Helper's highlights are exactly what pixel detection can follow. |
| 16 | **Death and risk**: **wilderness banned entirely** (Shortest Path set to avoid it). After a death: walk back, retrieve the grave (Death Indicator plugin + NPC highlight), re-gear and continue; **stop after a second death on the same step within an hour**. Notify on every death. A **gear value cap** for what the bot wears in combat. | |
| 17 | **Random events**: all event NPCs highlighted in a **danger color** and never clicked (wait, or pick another target). **Exception: the Genie**, whose lamp goes on a skill you choose. Ending up somewhere unexpected → pause and notify. | Ignored events leave by themselves; the risk is misclicks. |
| 18 | **Bank v2: Bank Tag layouts**, one tag tab per activity with items at fixed positions, **placeholders on**. Withdraw quantities via the quantity buttons; "as note" toggle; every withdraw verified via Inventory Tags. A withdraw that adds nothing = out of stock. Bank search is the fallback for one-off items. | Fixed bank slots break whenever the bank changes. |
| 19 | **Equipment**: automatic **tool ladders** (axes, pickaxes, harpoons and so on): the bot tells you when a better tier is unlocked, and uses it once it's in the gear tab. **Combat armour is a loadout you curate.** | Changed by #38: no automatic buying. |
| 20 | **Worlds**: members worlds only, from a favorites list of low-population worlds (no PvP, high-risk or total-level worlds). **Hop on crowding** (Player Indicators count 3+ other players at the target for 2+ minutes, contested resources, or busy combat targets), 5-minute cooldown, never in combat or mid-trip; if the whole list is busy, stay. Via World Hopper hotkeys. | Need to verify that hopping can be limited to members/favorite worlds on your client. |
| 35 | **Planning: method library + goals file + `--explain`.** The library holds each method's requirements, recipe (inputs/outputs/XP), location, bank tab, highlight setup and trust level. A short goals file says what you want (unlock targets, then all 99s, exclusions, manual items). The planner decides the next step; `skillbot plan --explain` shows what and why; any single choice can be overridden. Hand-written steps remain for one-off runs. | |
| 14 | **Training order: unlocks first, then rotation.** Short targets first: Magic for teleports (to ~45), Agility (~50), Construction (portal chamber etc.), combat 40s and money-makers. Then rotate all skills in time slices of a couple of hours, weighted by time to 99. Quest checkpoints notify you, and you mark them done (`skillbot quest-done "Plague City"`). | |
| 39–41 | **Prices from the official OSRS Wiki real-time prices API** (your server syncs with official prices; a descriptive User-Agent; polled politely; local history kept). Used for method choice within pools, shopping lists and Discord advice. **Alerts**: sell when a banked item is up ≥10% vs its 7-day average and the stack is worth ≥500k; buy when an upcoming supply is down ≥10% and the amount is worth ≥500k (each at most once per item per 24 h); method changes and profit warnings always; shopping list when supplies run out within ~12 h; everything else in the daily summary. All thresholds configurable. | No in-game GE interaction. |

## Skills

Levels are OSRS requirements. "Pool" means the planner picks between the options by
price and trust level. Quests marked (Q) are checkpoints, done by you or by the Quest
Helper follower.

### Gathering

| Skill | Plan |
|---|---|
| **Woodcutting** | trees 1–15 → oaks 15–30 → willows 30–60 (Draynor) → **yews at the Woodcutting Guild 60–90** → **redwoods (Guild) 90–99**. All banked. |
| **Mining** | copper/tin 1–15 → iron 15–30 (Varrock east mine → bank) → **Motherlode Mine 30–99**. No power-mining. |
| **Fishing** | shrimp/anchovies 1–20 (Draynor) → fly fishing 20–40 (Barbarian Village → Edgeville bank) → **lobsters at Catherby 40–68** → **Fishing Guild 68–82** (lobsters/swordfish, sharks at 76) → **minnows 82–99** once you have the full Angler outfit, otherwise sharks. **Fishing Trawler** (15+) runs as a bot activity (spam-click one spot) until the Angler outfit is earned. No barbarian fishing. |
| **Hunter** | Varrock Museum quiz (manual, to 9) → bird snares 9–29 → swamp/green salamanders 29–47 → red salamanders 47–63 → **red chinchompas 63–99** (Eagles' Peak (Q)). The Hunter plugin colors traps by state. |

### Processing

| Skill | Plan |
|---|---|
| **Cooking** | own banked fish at the **Hosidius kitchen** (lower burn rate, bank next door; favour no longer required, to verify on the server), sold afterwards. Wines dropped. |
| **Smithing** | bronze → iron → steel bars at a furnace with a bank 1–30 → **Blast Furnace 30–99**, pool of steel/mithril/adamant/runite bars by profit, **gold bars added after Family Crest (Q)**. Cannonballs (Dwarf Cannon (Q)) as the AFK fallback. |
| **Crafting** | pool: gem cutting vs glassblowing 1–63 → gem cutting (dragonstones 55+) vs dragonhide bodies vs glassblowing 63–99. All item-on-item. |
| **Fletching** | own logs → longbows (u), strung when bowstrings are cheap; darts (Tourist Trap (Q)) as an option. |
| **Herblore** | Druidic Ritual (Q) → clean herbs + the most profitable or least-loss potion per level bracket. |
| **Firemaking** | burning lines with the best logs 1–50 → **Wintertodt from 50**, as early as possible (food, warm clothing). |

### Combat and support

| Skill | Plan |
|---|---|
| **Attack / Strength / Defence / HP** | cows → **hill or moss giants to ~40** (banking bones and loot) → **crabs** for steady XP, alternating with **Slayer** for money. Styles rotated. |
| **Ranged** | crabs with **your own darts**; chinchompas probably not, under the profit rule. |
| **Magic** | teleport spells first → **High Alchemy (55+) on your own fletched longbows** → combat magic on crabs/Slayer as the alternative. |
| **Prayer** | pool: **ensouled heads** (Arceuus reanimation spells: 16/41/72/90 Magic, at the Dark Altar; spellbook switching) and a **public host's gilded altar** (Phials unnoting → Rimmington portal → altar; you set the host and mark the altar tile; fallback to ensouled heads if the host is offline) → your own gilded altar once Construction allows. No burying. |
| **Slayer** | semi-automatic: the kill count is read from the Slayer infobox; at 0 the bot gets a new task, **asks you on Discord which monster**, trains other things while waiting, then goes. Unsupported tasks are skipped (points) or handed to you. Masters Turael → Vannaka → Chaeldar → Nieve → Duradel. Starts with ~10 common monsters. |

### Other skills

| Skill | Plan |
|---|---|
| **Agility** | Gnome course 1–10 → rooftops Draynor 10, Al Kharid 20, Varrock 30, Canifis 40, Falador 50, Seers' 60, Pollnivneach 70, Rellekka 80, Ardougne 90. **Graceful first** from marks. Hallowed Sepulchre later. |
| **Thieving** | men 1–5 → tea stall 5–25 → fruit stalls (Hosidius) 25–55 → **Ardougne knights 55–99**; vyres after Sins of the Father (Q, by you). No blackjacking. |
| **Runecraft** | pool of options: fire runes (F2P), **Ourania altar (ZMI)**, **GOTR** (27+, Temple of the Eye (Q)), **Arceuus blood runes 77+**, **soul runes 90+**. No lava runes; Abyss banned (wilderness). |
| **Construction** | **bagged plants to 34** (also gets Farming to 34, ~650k gp) → pool: **oak larders → oak dungeon doors**, **mahogany tables** when gold is plentiful. Build the **portal chamber, restoration pool, gilded altar and jewellery box** as levels allow. Mahogany Homes later. |
| **Farming** | **bagged plants to 34** (with Construction) → **Tithe Farm 34–99** (golovanova → bologano 54 → logavano 74; gricoller's can, then the farmer's outfit). No herb, tree or fruit tree runs. |
| **Sailing** | deferred until everything else is proven. |

## Build order

### Phase 0: Real client
- [x] VM setup guide and scripts (Ubuntu 24.04 on Xorg, Java, RuneLite, the bot): [docs/vm-setup.md](docs/vm-setup.md), `scripts/vm/`, `skillbot doctor`
- [ ] You: set up the VM and send `debug.png` / `debug-skills.png`
- [ ] Calibrate, then validate the existing tasks on the real client: Draynor fishing (bank) first, then woodcutting, cooking, combat, runecrafting and run energy
- [ ] Replay test harness built from real screenshots

### Phase 0.5: Running unattended
- [x] Profiles, pause/resume with re-sync (location re-sync comes with navigation), RuneLite profile reminders
- [x] Supervisor and watchdog, VM autostart: [docs/unattended.md](docs/unattended.md)
- [x] Discord two-way bot, notifications, questions, commands, daily summary: [docs/discord.md](docs/discord.md) (price alerts come with the price service in Phase 1)
- [x] Color registry (`colors.yaml`), scene collision checks, `setup` / `check-setup` / `colors`
- [x] Trust levels (`run --supervised`, `trust`, promotion/demotion, trial slices and reports)

### Phase 1: Engine
- [x] Bank v2 (tag tabs, quantities, out-of-stock checks) and item-on-item processing
- [x] Navigation (teleport hubs, Shortest Path via map offsets) and dialogs: [docs/navigation.md](docs/navigation.md) (needs the first-run checks)
- [x] Death recovery, random-event avoidance and the Genie lamp, world hopping: [docs/safety.md](docs/safety.md)
- [x] Method library (`library/`), goals file, planner with `plan --explain`, `quest-done`
- [x] Price service, alerts, shopping lists, tool-upgrade notices: [docs/prices.md](docs/prices.md)

### Phase 2: Simple, high-value methods (the unlocks first)
- [x] Magic (teleports → alching): `cast` task + library
- [x] Agility (gnome course → all rooftops): `agility` task + library
- [x] Construction (bagged plants → larders/doors, mahogany tables): `construction` task + library (butler later)
- [x] Combat (cows → hill giants → sand/ammonite crabs): standing-combat mode + library
- [x] Woodcutting (Guild), Fishing (Catherby → Guild), Cooking (Hosidius), Fletching, Thieving (knights), Firemaking lines: library + `thieve` task, `bank_location` travel
- [ ] Crafting, Herblore, Runecraft (ZMI)

### Phase 3: Minigames and special mechanics
- [ ] Motherlode Mine, Blast Furnace, Tithe Farm, Wintertodt, Fishing Trawler, Hunter (chinchompas)
- [ ] Prayer (ensouled heads, public gilded altar), Arceuus runes
- [ ] Quest Helper follower (unlock quests), semi-automatic Slayer

### Phase 4: Later
- [ ] GOTR, Hallowed Sepulchre, Mahogany Homes, minnows
- [ ] Upgrades: darts, Giants' Foundry, vyres
- [ ] Sailing

## Things to verify early on the real client

- The world map recenters on the player when opened, and the zoom stays fixed (navigation depends on it).
- Inventory Tags are drawn while the bank is open.
- Object Markers persist inside player-owned houses (gilded altar host).
- World Hopper can be limited to members or favorite worlds.
- `tag:<name>` bank search opens a tag tab.
- The Hosidius kitchen is open without favour.
- Every default screen position in `layout.py` (inventory, tabs, skills tab, bank grid, login buttons, HP bar, run orb and energy number).
