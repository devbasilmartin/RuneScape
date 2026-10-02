# Discord

The bot talks to you through your own Discord bot: notifications, the daily summary,
questions you answer from your phone, and commands. It replaces the plain webhook.

It runs as its own service in the VM, separate from the supervisor, so `/status`,
`/screenshot` and `/start` keep working even when the supervisor has stopped.

## What you get

| | |
|---|---|
| **Notifications** | bot stopped (and why), supervisor gave up, deaths, 99s, finished steps, manual checkpoints |
| **Daily summary** | at 09:00 (VM time): time online, level-ups, restarts and stops, current step |
| **Questions** | e.g. "Which Slayer monster?": tap a button, or reply to the message with your own answer |
| `/status` | supervisor state, whether the bot is alive, current step and its progress |
| `/levels` | current levels |
| `/screenshot` | the VM's screen right now |
| `/pause`, `/resume` | hand over to yourself and back |
| `/start`, `/stop` | start or stop the supervisor (RuneLite and the bot) |
| `/questions` | questions still waiting for you |
| `/shopping`, `/sold ITEM` | what to buy for ~12h of training; clear an item you sold ([prices.md](prices.md)) |
| `/profile`, `/switch NAME` | which account is active; switch to another (restarts the supervisor) |

**Only you can use it:** commands, buttons and replies from anyone other than the account in
`SKILLBOT_DISCORD_OWNER` are refused. Keep the bot in a private server anyway.

## 1. Create a private server and channel

In Discord: **+** (Add a Server) → **Create My Own** → **For me and my friends**, then make a
channel such as `#skillbot`.

## 2. Create the Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application**, name it `skillbot`.
2. **Bot** page:
   - **Reset Token** → copy the token. This is a password for the bot; never share it.
   - Under *Privileged Gateway Intents*, turn on **Message Content Intent** (so it can read
     your replies to questions). Save.
   - Turn **Public Bot** off, so only you can add it to servers.
3. **OAuth2 → URL Generator:** tick scopes **bot** and **applications.commands**, then bot
   permissions **View Channels**, **Send Messages**, **Attach Files** and **Read Message History**.
   Open the generated URL and add the bot to your private server.

## 3. Find the two ids

In Discord: User Settings → Advanced → turn on **Developer Mode**. Then:
- right-click your `#skillbot` channel → **Copy Channel ID**
- right-click your own name → **Copy User ID**

## 4. Configure the VM

Add to `~/.config/skillbot/env`:

```sh
SKILLBOT_DISCORD_TOKEN="the bot token"
SKILLBOT_DISCORD_CHANNEL="the channel id"
SKILLBOT_DISCORD_OWNER="your user id"
```

You can remove `SKILLBOT_DISCORD_WEBHOOK`; with a token set, notifications go through the bot.

Then re-run the service installer (it adds the Discord service) and start it:

```sh
cd ~/skillbot
git pull
.venv/bin/pip install -r requirements.txt
bash scripts/vm/install-service.sh
systemctl --user start skillbot-discord
```

## 5. Test it

- In Discord, type `/status`. The commands appear within a few seconds of the service connecting.
- From the VM: `python -m skillbot ask "Does this work?" Yes No`, then tap an answer in
  Discord. The terminal prints what you chose.
- `/screenshot` should show the VM's desktop.

Logs: `data/discord.log`. Service state: `systemctl --user status skillbot-discord`.

## Settings

```yaml
discord:
  summary_hour: 9      # when the daily summary is sent, VM local time
```

To set the VM's time zone so that hour means yours:
`sudo timedatectl set-timezone America/New_York` (use your own zone; `timedatectl list-timezones` lists them).
