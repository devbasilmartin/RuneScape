# The control panel

A page in the VM's browser with a button for every everyday command, so you don't need
the terminal: it runs the same commands, shows their output live, lets you answer their
questions, and shows the images they write.

## Open it

Once (setup.sh does this for you on a new VM):

```sh
python -m skillbot ui --install
```

Then open **Skillbot** from the app grid (the dots at the bottom-left) or the desktop
icon. Or from a terminal: `python -m skillbot ui`. It opens at http://127.0.0.1:8765/ and
only this VM can reach it.

## What's on it

- **Run** (the top right card): **One activity** (pick an activity, optional minutes /
  level / bank-drop), **Schedules** (build, save and run named schedules; see
  [schedules.md](schedules.md)), **My plan** (config.yaml). **I'm watching** applies to all
  three.

- **Bot**: Stop (same as Ctrl+C); Pause / Resume; What's next? (`plan`); Accounts.
- **Check**: Screenshot (`debug`, shown below), Doctor, Check step (`check-setup`).
- **Setup**: Update bot (`git pull`; then close and reopen the panel), Calibrate,
  Build RuneLite profile (pick an export to recolor its markers).
- **Learn**: Teach levels (a form with a box per skill), Read levels, Skills screenshot,
  Run orb (`calibrate-run`), Run energy (`learn-energy`).

Commands that ask questions (Run orb, Run energy) print the question in **Output**:
type the answer and press Enter, or click **Just Enter** when it only wants Enter.

One command runs at a time: they all use the game's screen and the mouse.
