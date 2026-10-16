# Weekend testing

This is an order to try things in. Each step needs the ones before it. For each one:

1. Run **Check step** first.
2. Watch the run (Run → watching), and stop it if it does something daft.
3. Afterwards, write down roughly when anything went wrong, then use **Send to PC**. The black box keeps the last 80 seconds before any error, so you don't need to be recording.

Two hours of clean, watched running moves an activity from experimental to trial. After that, unattended runs can use it.

## 1. Travel (everything after cows needs it)
1. Install Shortest Path, mark the Lumbridge stairs, then run Calibrate map.
2. Teach a world-map right-click: Learn → `Set target` (or whatever the rows are) → Teach a menu, then hover the world map.
3. Try a short trip: stand in Lumbridge and run **bury bones (Draynor)** with bones in the bank.

You should see: the world map opens, a target is set, the bot walks along the pink line and opens the Draynor bank.

## 2. Banking
- **bury bones** or **big bones**: this tests withdrawing and the bank tab.
- **Fishing** at Draynor with banking.

## 3. Combat past cows
- **Al-Kharid warriors** (combat 20–40): the walk goes through the Al Kharid toll gate. The bot doesn't handle the gate's dialog yet. If it stops at the gate, Send to PC, and I'll teach it the dialog from your screenshot.

## 4. Quests (docs/quests.md)
1. Set up Quest Helper's colors and turn on Use Shortest Path.
2. Do Cook's Assistant, then Rune Mysteries.
3. Then try **air runes (Falador)**, which needs Rune Mysteries done.

## 5. The f2p all skills schedule, watched
Leave it on for an hour while you watch. Lines that can't start are skipped with a message, and those messages are the to-do list.

## What to send me
- Send to PC after any problem, plus the rough time it happened.
- Anything the panel's Check step marked FAIL that you couldn't fix.
- At the end of the weekend: the panel's **Last 24h** output, and Send to PC.
