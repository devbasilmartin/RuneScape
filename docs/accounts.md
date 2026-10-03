# Several accounts: progress log and rotation

Each account is a **profile** (its own config, plan or goals, calibration, levels and login;
see [unattended.md](unattended.md#several-accounts)). One account plays at a time, in the one
RuneLite client. This page covers seeing where every account is, and rotating between them.

## Where every account is

```sh
python -m skillbot accounts
```
```
**main** (playing) · on now until 14:30
  total level 812 · today 2.4h · all time 96.1h
  step: willows (woodcutting 58 → 60)
**alt** · next
  total level 455 · today 0.0h · all time 31.0h
  step: slayer (slayer 22 → 99)
  slayer: hill_giants, 31 left (12 tasks done)
**pure** · benched: plan complete
  ...
```

- `accounts --log main` shows that account's history: logins, every step with its level
  gains and duration, every stop and why. The history lives in
  `profiles/<name>/data/history.jsonl` (one JSON object per line), so it's easy to graph.
- `accounts --json` (and `accounts --log main --json`) give the same thing for your own scripts.
- Discord: **/accounts**.

## Rotating automatically

Copy `rotation.example.yaml` to `rotation.yaml` and list the accounts with the length of their
turns. You can also set a daily cap per account, a different goals file per turn, and the order:
`in_order`, `least_played_today` or `lowest_total_level`. Then run the supervisor as usual
(`systemctl --user restart skillbot`).

When a turn is over:
1. The supervisor asks the bot to hand over. The bot finishes its current batch (one
   inventory load or so), **logs out in game**, and exits.
2. After `gap_minutes`, the next account's bot starts and logs in with that profile's login.
   The client isn't restarted.
3. If a bot doesn't hand over within `handover_minutes`, it's stopped and the supervisor logs
   the game out itself.

An account whose bot stops on its own, for example with its plan complete or out of supplies
everywhere, is **benched**: the rotation skips it until you run
`python -m skillbot rotation unbench NAME`. You can bench one yourself with
`rotation bench NAME`. Stopping the bot yourself (mouse in a corner, Ctrl+C) still stops
everything. When every account is benched or at its daily cap, the game stays logged out until
one is eligible again (for example the next day).

`python -m skillbot rotation` prints the schedule. `pause` / `resume` still work, for the account
that's on. While paused nothing switches; a turn that ran out in the meantime (or a switch you
asked for) happens when you resume.

## Switching from scripts, cron, or your phone

```sh
python -m skillbot switch alt               # next turn: alt, for its usual hours
python -m skillbot switch pure --hours 0.5  # half an hour of pure
```

A switch is always the clean handover above, picked up within about 15 seconds. Discord's
**/switch NAME** and `profile use NAME` do the same while the supervisor runs. Without
`rotation.yaml`, switching is the only way accounts change: the requested account plays until
the next switch.

So any schedule you can express in a script works. For example, with cron, the main account
on weekday evenings and the alt otherwise:

```cron
0 18 * * 1-5  cd ~/skillbot && .venv/bin/python -m skillbot switch main --hours 5
0 23 * * *    cd ~/skillbot && .venv/bin/python -m skillbot switch alt --hours 19
```

Or a script that picks whoever is furthest behind in Slayer:

```python
import json, subprocess
data = json.loads(subprocess.check_output(
    [".venv/bin/python", "-m", "skillbot", "accounts", "--json"]))
behind = min(data["accounts"], key=lambda a: a["levels"].get("slayer", 1))
subprocess.run([".venv/bin/python", "-m", "skillbot", "switch", behind["profile"], "--hours", "2"])
```

## Check on the real client first

- The logout tab and the "Click here to logout" button are estimated positions
  (`layout.tabs.logout`, `layout.logout_button`). Try `python -m skillbot logout` once while
  watching.
- Each profile needs its own `calibrate` the first time, although with the same client and
  window position the values come out the same.
