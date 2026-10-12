# Getting screenshots and logs from the VM to Claude

Two ways, and they work together:

1. **Shared folder**: a folder on your PC that the VM can write to. The panel's
   **Send to PC** button drops a screenshot, the bot's images and its log there; you drag
   them into the chat.
2. **Claude Code in the VM**: a Claude session running *on* the VM sees the screen, the
   images and the logs itself. Nothing to copy at all.

## 1. Shared folder (about 10 minutes, once)

On the **PC**: make a folder, e.g. `C:\Users\<you>\skillbot-share`.

In the **VM's window** (the VirtualBox menu bar; if you can't see it, press the right
Ctrl key + Home to bring up the menu):
**Devices → Shared Folders → Shared Folders Settings…** → the folder-with-a-+ icon:

- Folder Path: the folder you made
- Folder Name: `pc`
- tick **Auto-mount** and **Make Permanent** → OK → OK

(Or in PowerShell on the PC, with the VM powered off:
`& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" sharedfolder add skillbot --name pc --hostpath "$HOME\skillbot-share" --automount`)

In the **VM**, in a terminal:

```sh
cd ~/skillbot && git pull
bash scripts/vm/share.sh
```

It does one step at a time and tells you when to restart or log out and back in; run it
again after each restart until it says **Shared folder ready**. (It installs VirtualBox's
guest tools if they're missing; the same tools make copy/paste between PC and VM work:
**Devices → Shared Clipboard → Bidirectional**.)

### Using it

- Panel: **Check → Send to PC**. Works while the bot runs.
- Terminal: `python -m skillbot share`.

On the PC, open your folder → `skillbot` → the newest folder (named by date and time). It
has `screen.png` (the whole VM screen), `debug.png` and the other images, `skillbot-log.txt`
(the end of the bot's log) and `panel-output.txt` (the panel's Output). Drag what's
relevant into the chat. The newest 10 sends are kept.

## 2. Claude Code in the VM

A session on the VM can run the bot's commands, look at the images they write, take
screenshots (`python -m skillbot screenshot`), read the log and fix code, without you
copying anything. `CLAUDE.md` in the repo tells it the project's rules and where things
stand.

In a terminal in the VM:

```sh
curl -fsSL https://claude.ai/install.sh | bash
# open a new terminal so `claude` is found, then:
cd ~/skillbot
claude                  # log in once, then /exit
claude remote-control
```

Leave that terminal open: the session shows up in the Claude Code app on your PC or phone,
and you talk to it from there. It runs as you on the VM, so it can read everything you
can (including `~/.config/skillbot/env`, which `CLAUDE.md` tells it never to print).

A few things to know:
- It's a new conversation: it knows the repo, not this chat. Tell it what you were doing.
- The bot moves the mouse. Don't have the session click around the screen while a run is
  going; reading screenshots and logs is fine.
- The repo is public. Screenshots show your account name, so they stay out of git
  (`.gitignore` covers the bot's images).
