# Quests

The bot follows RuneLite's **Quest Helper** plugin. Quest Helper highlights what to do next, and the bot:

- clicks the highlighted chat option, NPC or object;
- uses highlighted inventory items on things;
- presses space through "Click here to continue".

When nothing is highlighted for a while, it stops and tells you. That happens when a step needs you (a puzzle, a fight, a step Quest Helper only explains in text) or when the quest is finished.

**Getting the items is your job.** The bot never buys anything.

The quest list is `library/quests/f2p.yaml`. For each quest it gives:

- where the quest starts (the bot walks there);
- the levels you need;
- the items to bring;
- the steps that need you;
- the rewards.

## Set up once

1. Install **Quest Helper** from the Plugin Hub.
2. In Quest Helper's settings, set its highlight colors to the bot's colors (`docs/markers.md` lists them):
   - NPCs and objects: `quest_target`
   - the chat option: `quest_dialog`
   - inventory items: `quest_item`
3. Teach the quest names, so the bot can see when a quest is finished:
   1. Open the quest tab in game.
   2. In the panel, go to Learn, pick the quest and click **Teach a quest**.
   3. Hover the quest's name in the tab and click **Just Enter**.

   Do this for each quest you'll run. If the bot doesn't know a quest's name, you mark the quest done yourself (Quest done).
4. In Quest Helper's settings, turn on **Use Shortest Path**. Quest Helper then draws a route to the next step, and when nothing is highlighted the bot walks along it. Without it, the bot stops when the next NPC is off screen.

## Do a quest while you watch

1. In the panel, click **Quests**. Each quest shows as done, ready, or what it still needs.
2. Get the items it lists.
3. Start the quest in Quest Helper (select it in the sidebar).
4. Under Learn, pick the quest. Click **Check step** with the quest picked, then **Do quest**.

You should see the bot walk to the start, talk to the NPC, and pick the highlighted chat options. When it stops:

- If you get a message about a step that needs you, do that step by hand, then click **Do quest** again.
- If the quest is finished and its name was taught, the bot marks it done itself. If its name wasn't taught, click **Quest done**.

## In schedules

A schedule line can be a quest: `- {quest: "Rune Mysteries", minutes: 40}`. In the panel, quests are at the bottom of the activity list, under "quests".

A quest line:

- is skipped once the quest is finished;
- is skipped (with one message per run) when you don't have the levels, or haven't said its items are ready. Once you've got them, pick the quest and click **Items ready** (or run `quest-ready NAME`).
- like any new activity, starts as experimental. Watched runs do it; unattended runs skip it until it has earned trust.

Methods that need a quest (Runecraft needs Rune Mysteries) wait until it's done. **auto** lines pick them up from then on.

The bot comes with two built-in schedules:

- **f2p quests:** the easy quests, once each.
- **f2p all skills:** the same quests first, then every skill.

## The quests

Easiest first: Cook's Assistant, Sheep Shearer, Rune Mysteries, The Restless Ghost, X Marks the Spot, Doric's Quest, Imp Catcher, Witch's Potion, Romeo & Juliet, Goblin Diplomacy.

These are in the list but need you for part of them:

- **The Knight's Sword:** the portrait, and the Ice Dungeon.
- **Vampyre Slayer:** the Count fight.
- **Ernest the Chicken:** the lever puzzle.

## Not measured yet

The quest tab's position (`layout.quest_list`, and the tab button at 604,186) is a guess. If teaching a quest says "no quest names found" with the tab open, send a screenshot (Send to PC).
