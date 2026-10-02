#!/usr/bin/env bash
# One-time setup of the bot VM (Ubuntu Desktop 24.04). Run as your normal user:
#   bash scripts/vm/setup.sh
# Safe to run again; every step checks before changing anything.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
say() { printf '\n==> %s\n' "$*"; }

if [[ $EUID -eq 0 ]]; then
    echo "Run this as your normal user, not root (it uses sudo where needed)." >&2
    exit 1
fi

say "Installing packages"
sudo apt-get update
sudo apt-get install -y \
    git python3-venv python3-dev python3-tk \
    openjdk-17-jre x11-utils xdotool scrot

say "Forcing the Xorg session (pyautogui cannot control Wayland)"
GDM_CONF=/etc/gdm3/custom.conf
if grep -qE '^\s*WaylandEnable\s*=\s*false' "$GDM_CONF"; then
    echo "already set"
else
    sudo sed -i 's/^#\?\s*WaylandEnable\s*=.*/WaylandEnable=false/' "$GDM_CONF"
    grep -qE '^WaylandEnable=false' "$GDM_CONF" || \
        sudo sed -i '/^\[daemon\]/a WaylandEnable=false' "$GDM_CONF"
    echo "set WaylandEnable=false in $GDM_CONF (takes effect after a reboot)"
fi

say "Turning on automatic login for $USER"
if grep -qE "^\s*AutomaticLogin\s*=\s*$USER" "$GDM_CONF"; then
    echo "already set"
else
    sudo sed -i '/^\s*#\?\s*AutomaticLoginEnable\s*=.*/d; /^\s*#\?\s*AutomaticLogin\s*=.*/d' "$GDM_CONF"
    sudo sed -i "/^\[daemon\]/a AutomaticLoginEnable=true\nAutomaticLogin=$USER" "$GDM_CONF"
    echo "done"
fi

say "Disabling screen blanking, lock screen and notifications"
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.screensaver idle-activation-enabled false
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
gsettings set org.gnome.desktop.notifications show-banners false
gsettings set org.gnome.desktop.interface enable-animations false

say "Stopping update pop-ups from covering the game"
gsettings set com.ubuntu.update-notifier no-show-notifications true 2>/dev/null || true
gsettings set com.ubuntu.update-notifier regular-auto-launch-interval 36500 2>/dev/null || true
sudo tee /etc/apt/apt.conf.d/99skillbot-no-auto-upgrade >/dev/null <<'CONF'
// Updates are installed by hand (sudo apt upgrade) so nothing restarts mid-run.
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
CONF

say "Python environment for the bot"
if [[ ! -d "$REPO_DIR/.venv" ]]; then
    python3 -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

if [[ ! -f "$REPO_DIR/config.yaml" ]]; then
    cp "$REPO_DIR/config.example.yaml" "$REPO_DIR/config.yaml"
    echo "created config.yaml from config.example.yaml"
fi

say "Done. Reboot now (sudo reboot), then run: bash scripts/vm/check.sh"
