# Running unattended (Phase 0.5)

Once the bot runs correctly by hand ([vm-setup.md](vm-setup.md)), this makes it start by
itself and recover from crashes, hangs and frozen clients.

## How it works

`python -m skillbot supervise` runs as a background service inside the VM. It:

1. starts RuneLite (`scripts/vm/start-client.sh`), waits for its window, and **moves it to
   the top-left corner**, so the calibrated game position is the same after every restart;
2. starts the bot;
3. checks every 15 seconds:

| What it sees | What it does |
|---|---|
| The bot crashed (an error exit) | Restarts the bot |
| The bot hasn't written its heartbeat for 3 minutes (hung) | Restarts the bot |
| RuneLite exited | Restarts RuneLite and the bot |
| The game screen hasn't changed for 5 minutes (frozen) | Restarts RuneLite and the bot |
| The bot stopped **by itself** (plan done, a setting said stop, you moved the mouse into a corner) | Leaves it stopped, notifies you, and exits |
| More than 5 restarts within an hour | Gives up, notifies you, and exits, so a broken setup can't loop forever |
| `pause` | Stops the bot and the checks until `resume` |

After a restart the bot logs back in (with `on_logout: relogin`), re-reads its levels and
continues the plan.

## 1. Credentials and settings

Edit `~/.config/skillbot/env` (created in VM setup step 7) so it holds:

```sh
CLIENT_CMD="java -jar $HOME/client/RuneLite.jar"
SKILLBOT_USERNAME="your login"
SKILLBOT_PASSWORD="your password"
```

For notifications, questions and phone commands, set up the Discord bot in
[discord.md](discord.md); it adds three more lines to this file.

The install script makes this file readable only by you. In `config.yaml`, set
`on_logout: relogin` so the bot logs back in after restarts and disconnects.

## 2. Install the service

```sh
cd ~/skillbot
bash scripts/vm/install-service.sh
systemctl --user start skillbot
```

From now on it starts by itself about 20 seconds after the VM logs in.

**Calibrate with the window where the supervisor puts it.** The supervisor moves RuneLite to
the top-left of the screen. If you calibrated with the window somewhere else, run
`python -m skillbot pause`, then `calibrate` again, then `resume`.

## 3. Everyday commands

| | |
|---|---|
| `python -m skillbot pause` | Stop the bot to play yourself (switch RuneLite to your own profile) |
| `python -m skillbot resume` | Hand back to the bot (switch back to the `bot` profile first) |
| `systemctl --user status skillbot` | Is the supervisor running? |
| `tail -f data/supervisor.log` | What the supervisor is doing |
| `tail -f data/skillbot.log` | What the bot is doing |
| `systemctl --user stop skillbot` | Stop everything (RuneLite too) |
| `bash scripts/vm/install-service.sh --remove` | Uninstall the service |

Run `python -m skillbot ...` commands from `~/skillbot` with the virtual environment active
(`source .venv/bin/activate`).

## 4. Start the VM with Windows

In PowerShell on Windows, in the folder where you have this repository (or copy the one
script over):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\autostart-vm.ps1
```

The VM then starts, without a window, one minute after you log in to Windows. To watch it,
open VirtualBox, select the VM and click **Show**. Closing that window with "Continue running
in the background" keeps it running.

Two Windows settings decide how well this survives restarts:

- **Windows Update:** Settings → Windows Update → Advanced options → **Active hours**. Set them
  to cover when you use the PC, so automatic restarts happen at predictable times.
- **Logging in after a reboot:** the VM only starts once you log in to Windows. Windows can log
  in automatically after an update restart (Settings → Accounts → Sign-in options → "Use my
  sign-in info to automatically finish setting up after an update"). Fully automatic sign-in
  at every boot is possible too, but it means anyone with physical access to the PC gets in,
  so only do that if you're comfortable with it.

## Several accounts

Each account gets a **profile**: its own config, plan, calibration, learned digits, levels
and login. One account runs at a time.

```sh
python -m skillbot profile create main      # then put its login in the file it names
python -m skillbot profile create alt
python -m skillbot profile use main         # the account the services run (restarts them)
python -m skillbot profile list
```

Every command works on the active profile, or on another one with `--profile NAME`, e.g.
`python -m skillbot --profile alt calibrate`. Each profile needs its own calibration and
learned digits the first time. The login goes in `~/.config/skillbot/profiles/NAME.env`
(`SKILLBOT_USERNAME`, `SKILLBOT_PASSWORD`). Discord stays one channel for all accounts:
messages are tagged with the profile, and `/switch NAME` changes account from your phone.

Without any profiles, the top-level `config.yaml` and `data/` are used as before.

To see every account's progress, or to rotate between accounts on a schedule (or from your
own scripts), see [accounts.md](accounts.md).

**Handing over and back:** `pause` stops the bot; play as much as you like, anywhere. On
`resume` the bot starts fresh: it closes open interfaces, opens the inventory, resets the
camera and re-reads all levels before continuing. (Walking back from wherever you left the
character comes with the navigation work in Phase 1; until then, park the character near
the current activity before resuming.)

## Tuning

The defaults can be changed in `config.yaml`:

```yaml
supervisor:
  poll_seconds: 15
  heartbeat_minutes: 3
  freeze_minutes: 5
  max_restarts_per_hour: 5
  client_start_timeout: 180     # seconds to wait for the RuneLite window
  client_settle_seconds: 30     # then this long for it to finish loading
  window_name: RuneLite         # part of the client's window title
  window_position: [0, 0]
```

If your client's window title doesn't contain "RuneLite", set `window_name` to part of it.
`xdotool search --name RuneLite getwindowname` shows what it finds.

## Troubleshooting

| Problem | Fix |
|---|---|
| `systemctl --user status skillbot` shows errors about the display | Log out and back in, or run `systemctl --user import-environment DISPLAY XAUTHORITY` then `systemctl --user restart skillbot`. |
| It says "the client window never appeared" | Check `CLIENT_CMD` by running `bash scripts/vm/start-client.sh` yourself, and check `window_name`. |
| The bot restarts every few minutes with "no heartbeat" | The bot is stuck in a way it can't see; look at the end of `data/skillbot.log` before each restart and send it to me. |
| Clicks land in the wrong place after a restart | The window wasn't at the supervisor's position when you calibrated; see step 2. |
