# skillbot: notes for Claude

skillbot trains an Old School RuneScape account by reading the screen: RuneLite plugins
draw highlights in known colors, and the bot finds those colors and clicks them. The
server is a private one that allows bots and mimics the real game, F2P worlds included.
The client is a modified RuneLite AppImage (`~/client/RuneLite.AppImage`, from the
server's Discord), fixed mode, in an Ubuntu 24.04 VirtualBox VM on the owner's Windows PC.
The VM user is `basil` and the repo is at `~/skillbot`. The goal: 99s, several accounts,
and the owner can always take over and play by hand.

Start with `README.md`, `ROADMAP.md` (the original design decisions) and
`docs/modes-plan.md` (the current build order).

## Rules from the owner (don't break these)

- **Credentials** only come from env vars (`SKILLBOT_USERNAME` / `SKILLBOT_PASSWORD` in
  `~/.config/skillbot/env` or a profile's env file). Never print, log, commit or paste them.
- **Discord** commands answer only `SKILLBOT_DISCORD_OWNER`.
- **The Grand Exchange is manual.** The bot never buys or sells. **No Wilderness.**
- **No anti-detection or "realism" tuning.** Mouse A/B testing stays off by default.
  **Check with the owner before changing any default behaviour.**
- **No pull requests unless asked.** Work on the branch the VM has checked out
  (`ccr-1dfa4c6b-dtavpx` unless told otherwise); don't push to other branches.
- No AI model names or ids in commits, code or docs.
- **The repo is public.** Screenshots show the account name (chatbox, title bar), so
  images never go into git. `.gitignore` covers the bot's images; check `git status`
  before committing anyway. Test images get cropped so no name shows
  (`tests/data/fixed_canvas_real.png`).

## Working on the VM

- **The bot owns the mouse while it runs.** Don't click, type or move windows during a
  run. Reading screenshots and logs is fine. Stop a run from the panel (Stop), with
  Ctrl+C, or by moving the mouse into a screen corner.
- Look at the screen: `python -m skillbot screenshot` (whole screen → `screen.png`),
  `python -m skillbot debug` (the game canvas with everything the bot detects →
  `debug.png`; it also prints the tagged slots, empty slots and HP).
- Other checks: `levels` (skills tab must be open), `doctor`, `check-setup STEP`,
  `calibrate` (when the RuneLite window moved: it finds the frame by template matching).
- The run log: `data/skillbot.log`. The control panel (`python -m skillbot ui`,
  http://127.0.0.1:8765) runs the same commands with buttons, and is how the owner
  usually works; its **Send to PC** puts the screen, images and log in the VirtualBox
  shared folder (`docs/file-sharing.md`).
- Per-machine state lives in `data/` and `config.yaml` (both ignored by git): the
  calibrated canvas origin, learned digit glyphs (`digits.json`, `energy_digits.json`),
  trust, progress.
- Pushing needs GitHub credentials on the VM. If they aren't set up, commit and say so.

## Developing

- Tests: `python -m pytest -q` (about 3 minutes, all must pass). The game is simulated in
  `tests/fakes.py` (`make_game`, `put_item`, `outline`, `blank`).
- **Real-client measurements beat guesses.** Layout values in `skillbot/layout.py`
  marked "measured on a real client" came from the owner's screenshots (skills tab, HP
  bar, empty inventory slots, the frame artwork in `skillbot/fixed_frame.json`). When
  something doesn't line up, get a real screenshot, measure, fix the value, add a test.
- **Colors** live in `colors.yaml` (the registry). `Registry.check` must stay clean:
  colors that are too close clash, and world highlights must stay away from the game's
  text colors. Renamed colors keep an alias in `colors.RENAMED` so old configs still
  load. After changing colors or the library, regenerate the marker list:
  `python -m skillbot marker-list` (a test compares it).
- **Library** (`library/*.yaml`): training methods with levels, location and a plan step.
  Schedules (`skillbot/schedule.py`) run them for a time or to a level. Trust levels:
  experimental → trial (2 clean supervised hours) → trusted; unattended runs skip
  experimental steps.
- Match the surrounding code: short docstrings that say why, plain names, few comments.
  Docs are written for the owner: plain words, numbered steps, what they should see.

## Where things stand

Working on the real client: calibration, inventory tags, reading levels, woodcutting
(chop and drop, oaks), cows (combat with eating below 50% HP, drop hides and beef, wait
for respawns, don't start a second fight), the control panel, schedules (one activity or
a named schedule, then log out).

Next, in order (`docs/modes-plan.md`): the HP guard for every activity, F2P/members
modes, cows + fire cooking, more F2P gathering methods.

Open:
- No travel destinations are recorded, so an activity has to be started where it
  happens; a schedule that moves between places stops when it tries to travel.
- The level font doesn't know the digit 9 yet (`learn-digits` with a 9 on screen).
- Run energy: a "1" doesn't split in `learn-energy` (needs `energy-check.png`).
- The VM doesn't draw the mouse cursor; a software cursor
  (`/etc/X11/xorg.conf.d/20-swcursor.conf`) was suggested but not confirmed.
