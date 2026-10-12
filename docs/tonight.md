# Tonight: set-up checklist

Everything new, in order. Each part says what you should see. Do them with the bot
stopped. If a part goes wrong, skip it, carry on, and tell me which step.

## 1. Update (2 min)

- [ ] Panel → Setup → **Update bot**. Close the panel and open it again.
- [ ] You should see a **Record** card, and **Calibrate map** under Setup.
- [ ] Setup → **Build RuneLite profile** (pick your export), then import
      `bot-profile.properties` in RuneLite: it tags the new items (iron ore, salmon,
      burnt meat).
- [ ] If the account is F2P: add `account: f2p` to `config.yaml`.

## 2. Shared folder (10 min) — [file-sharing.md](file-sharing.md)

- [ ] On the PC: make a folder `C:\Users\<you>\skillbot-share`.
- [ ] VM window menu (right Ctrl + Home if hidden) → **Devices → Shared Folders → Shared
      Folders Settings…** → folder-with-a-+ → Folder Path: that folder, Folder Name: `pc`,
      tick **Auto-mount** and **Make Permanent** → OK.
- [ ] VM terminal: `bash ~/skillbot/scripts/vm/share.sh`. Restart or log out when it says
      to, then run it again, until **Shared folder ready**.
- [ ] Panel → Check → **Send to PC**. On the PC: your folder → `skillbot` → newest folder
      has `screen.png` and `skillbot-log.txt`.

## 3. GitHub, then make the repo private (5 min)

- [ ] VM terminal:
      ```sh
      sudo apt install gh
      gh auth login        # GitHub.com → HTTPS → log in with a web browser
      gh auth setup-git
      ```
- [ ] Panel → **Update bot** still works (no password question).
- [ ] On GitHub: the repo → Settings → Danger Zone → **Change visibility → Private**.
- [ ] **Update bot** once more: still works. Tell me it's private.

## 4. Levels: the digit 9 (2 min)

- [ ] In game, open the skills tab (defence 19 shows a 9).
- [ ] Panel → Learn → **Teach levels…**, fill in the boxes, send.
- [ ] **Read levels**: no "could not read" lines.

## 5. Discord (20 min) — [discord.md](discord.md)

- [ ] Steps 1–4 of discord.md (server, bot, ids, env file).
- [ ] `bash ~/skillbot/scripts/vm/install-service.sh --discord-only`, then
      `systemctl --user start skillbot-discord`.
- [ ] On your phone: `/status` answers; `/screenshot` shows the VM.

## 6. Travel (15 min) — [travel.md](travel.md)

- [ ] RuneLite → wrench → **Plugin Hub** → install **Shortest Path**. Path color `#FF0080`,
      on the minimap and in the world, avoid the Wilderness, clear the target on arrival.
- [ ] Object Markers on the **Lumbridge castle south staircase**, all three floors, color
      `#C000C0`.
- [ ] In Lumbridge: Panel → Setup → **Calibrate map**: hover the castle courtyard → **Just
      Enter**, hover the middle of the cow field → **Just Enter**. You see
      `saved: N pixels per tile`. Don't zoom the world map from now on.
- [ ] Panel → Record (keep everything), then, standing at the cows, in a terminal:
      `python -m skillbot travel "lumbridge bank" --from "lumbridge cows" --until bank`.
      It should walk to the castle, climb to the top and stop by the booths.
      Stop recording → **Send recording to PC**.

## 7. A test run (as long as you like)

- [ ] At the cows with a few pieces of food: **One activity → cows → Start**, bank or drop.
- [ ] Watch it eat below half HP (the HP guard). With **bank**, a full inventory should walk
      to Lumbridge bank and back.
- [ ] Anything odd: note the time, Record if it's still going, **Send recording to PC**,
      and send me `frames.png` with the time.
