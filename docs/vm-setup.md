# VM setup (Phase 0)

This sets up a VirtualBox virtual machine on your Windows PC that runs RuneLite and the
bot. The bot's mouse and keyboard live inside the VM, so you can keep using your PC
while it plays. Plan on about an hour, most of it waiting for downloads and installs.

What you'll end up with: Ubuntu Desktop 24.04 in a VM with 4 GB RAM and 2 CPU cores,
logging in automatically to an Xorg desktop that never sleeps or locks, with RuneLite
and the bot installed.

## 1. Prepare Windows

1. **Check virtualization is on.** Open Task Manager → Performance → CPU and look for
   *Virtualization: Enabled*. If it says Disabled, turn on Intel VT-x / AMD-V (sometimes
   called "SVM") in your BIOS/UEFI settings.
2. **Download:**
   - VirtualBox for Windows hosts: <https://www.virtualbox.org/wiki/Downloads>. Install it with the defaults.
   - Ubuntu **24.04 LTS Desktop** ISO: <https://ubuntu.com/download/desktop>.
3. **Disk space:** the VM needs about 40 GB.

## 2. Create the VM

In VirtualBox: **Machine → New**.

| Setting | Value |
|---|---|
| Name | `skillbot` |
| ISO Image | the Ubuntu ISO you downloaded |
| **Skip Unattended Installation** | **tick it** (we'll install by hand so you choose the settings) |
| Base Memory | **4096 MB** |
| Processors | **2** |
| Hard Disk | **40 GB**, dynamically allocated (leave "Pre-allocate" off) |

Click **Finish**, then select the VM and open **Settings** before starting it:

- **Display → Screen:** Graphics Controller **VMSVGA**, Video Memory **128 MB**,
  **Enable 3D Acceleration: off**.
- **System → Motherboard:** Pointing Device **USB Tablet** (the default).
- Everything else can stay at the defaults (NAT networking is fine).

## 3. Install Ubuntu

Start the VM and follow the installer:

1. **Try or Install Ubuntu** → language → **Install Ubuntu**.
2. **Interactive installation** → **Default selection**.
3. Tick **Install third-party software** (graphics and media drivers).
4. **Erase disk and install Ubuntu.** This only erases the VM's virtual disk, not your PC.
5. Create your user, e.g. name `bot`, and a password you'll remember. Choose
   **Require my password to log in**; the setup script switches on automatic login later.
6. Wait for it to finish, click **Restart now**, and press Enter when it asks you to
   remove the installation medium.

Log in, and skip through the welcome screens (no need for Ubuntu Pro or a Livepatch account).

## 4. Get the bot onto the VM

Open **Terminal** (press the Windows key, type "terminal") and run:

```sh
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/devbasilmartin/RuneScape.git ~/skillbot
cd ~/skillbot
git checkout ccr-1dfa4c6b-dtavpx    # the branch with the latest work, until it's merged
```

If the repository is private, Git asks for a username and password. Use your GitHub
username and a **personal access token** as the password: GitHub → Settings → Developer
settings → Personal access tokens → **Fine-grained tokens** → *Generate new token*,
limited to this one repository with **Contents: Read-only**.

## 5. Run the setup script

Still in the terminal, on the VM's desktop (not over SSH):

```sh
bash scripts/vm/setup.sh
sudo reboot
```

The script:
- installs Python, Java 17 and the X11 tools the bot uses
- **turns off Wayland** so the desktop runs on Xorg, which pyautogui needs
- turns on **automatic login**
- disables **screen blanking, the lock screen, notification banners and animations**
- stops automatic updates and update pop-ups from covering the game
- creates the bot's Python environment (`.venv`) and a `config.yaml`

It's safe to run again if anything fails halfway.

## 6. Set the screen size

After the reboot the VM should log you in by itself. Open **Settings → Displays** and set
the resolution to **1280 × 800** (1440 × 900 also works). A fixed resolution keeps every
calibrated screen position valid.

In VirtualBox's menu, make sure **View → Auto-resize Guest Display** is *off*, so resizing
the VM window never changes the resolution.

## 7. Install your RuneLite client

Copy or download your server's modified RuneLite into the VM, e.g. into `~/client/`. The
easiest way is to download it inside the VM the same way you got it on Windows.

Tell the bot how to start it:

```sh
mkdir -p ~/.config/skillbot
nano ~/.config/skillbot/env
```

Put in **one** line matching your client, then save (Ctrl+O, Enter, Ctrl+X):

```sh
CLIENT_CMD="java -jar $HOME/client/RuneLite.jar"       # if it's a .jar
# CLIENT_CMD="$HOME/client/RuneLite.AppImage"          # if it's an AppImage (chmod +x it first)
```

Then start it:

```sh
bash scripts/vm/start-client.sh
```

## 8. RuneLite settings for the bot

In RuneLite:

1. **Profiles:** in the configuration panel, open **Profiles** and create one called **`bot`**.
   Switch to it. All bot highlights live in this profile, so your own profile stays clean.
2. **Fixed mode:** after logging in, open the game's settings (the wrench icon) → *Display* →
   *Game client layout* → **Fixed - Classic layout**. Don't resize the RuneLite window afterwards.
3. **GPU plugin: off.** Software rendering is more reliable in a VM.
4. Zoom the camera all the way out, and set up the highlights from the README for
   your first test: Draynor fishing (fishing spots, the bank booth, Inventory Tags on the fish).

## 9. Check everything

From a terminal on the VM's desktop:

```sh
cd ~/skillbot
bash scripts/vm/check.sh
```

Everything should be **PASS**, except **calibration**, which stays WARN until the next step.
Each FAIL says what to fix.

## 10. Calibrate and send me a screenshot

With RuneLite logged in, in fixed mode:

```sh
source .venv/bin/activate
python -m skillbot calibrate          # hover the top-left pixel of the game area, press Enter
python -m skillbot debug              # writes debug.png
```

Open `debug.png` (double-click it in the Files app) and send it to me. Then open the skills
tab and run `python -m skillbot debug --skills --out debug-skills.png` and send that too.
From those two I'll correct every screen position in one go before the first real run.

## 11. Take a snapshot

Once `check.sh` passes, take a snapshot so you can always get back to a working setup:
in VirtualBox, **Machine → Take Snapshot**, name it `clean setup`.

## Next: running unattended

Once the first real runs work, follow [unattended.md](unattended.md) to make the bot start by
itself and recover from crashes.

## Using the VM day to day

- **Leave the mouse alone inside the VM window while the bot runs.** With mouse integration on,
  moving your mouse over the VM window moves the bot's cursor too. Minimize the VM window,
  or toggle **Input → Mouse Integration** off while it runs.
- **Stop the bot** by moving its mouse into a screen corner, or by pressing Ctrl+C in its terminal.
- **Updates:** run `sudo apt update && sudo apt upgrade` yourself when the bot is stopped, and
  `git pull` in `~/skillbot` to get new bot versions.

## Troubleshooting

| Problem | Fix |
|---|---|
| VirtualBox says VT-x/AMD-V is not available | Enable virtualization in the BIOS (step 1). |
| The VM is very slow, with a green turtle icon in the status bar | Windows' Hyper-V is in use, so VirtualBox runs in a slow compatibility mode. Turning off *Hyper-V*, *Virtual Machine Platform* and *Core isolation → Memory integrity* in Windows fixes it, but Memory integrity is a security feature, so decide whether the speed is worth it. A slower VM still works if the game runs smoothly enough. |
| `check.sh` says Wayland | Re-run `scripts/vm/setup.sh` and reboot. At the login screen you can also pick **Ubuntu on Xorg** with the gear icon. |
| The game window is black or flickers | Make sure the GPU plugin is off. `start-client.sh` already forces software rendering. |
| The screen goes blank or locks after a while | Re-run `scripts/vm/setup.sh` from the desktop terminal (its settings only apply to the logged-in user). |
| `pyautogui` errors about Xlib or DISPLAY | Run bot commands from a terminal on the VM's own desktop, not over SSH. |
