#!/usr/bin/env bash
# Shared folder between the VM and the PC (docs/file-sharing.md). Run inside the VM:
#   bash ~/skillbot/scripts/vm/share.sh
# Safe to run again: each run does the next missing step and says what's left.
set -euo pipefail

say() { printf '\n==> %s\n' "$*"; }

# 1. VirtualBox's guest tools (they mount the shared folder)
if ! command -v VBoxControl >/dev/null 2>&1; then
    say "Installing VirtualBox's guest tools (asks for your password)"
    sudo add-apt-repository -y multiverse       # where Ubuntu keeps the VirtualBox packages
    sudo apt-get update -qq
    sudo apt-get install -y virtualbox-guest-utils virtualbox-guest-x11
    say "Done. Restart the VM (top-right menu → Power Off/Log Out → Restart), then run this again."
    exit 0
fi

# 2. Your user may open shared folders (group vboxsf)
if ! getent group vboxsf | grep -qw "$USER"; then
    say "Letting $USER open shared folders (asks for your password)"
    sudo usermod -aG vboxsf "$USER"
    say "Done. Log out and back in (or restart the VM), then run this again."
    exit 0
fi
if ! id -nG | grep -qw vboxsf; then
    say "You were added to vboxsf, but this login doesn't have it yet: log out and back in (or restart), then run this again."
    exit 0
fi

# 3. The folder from the PC, mounted by VirtualBox as /media/sf_<name>
shopt -s nullglob
shares=(/media/sf_*)
if [ ${#shares[@]} -eq 0 ]; then
    cat <<'MSG'

==> No shared folder yet. On the PC, in the VM's window:
    Devices → Shared Folders → Shared Folders Settings… → the folder-with-+ icon
      Folder Path:  a folder on your PC, e.g. C:\Users\<you>\skillbot-share (make it first)
      Folder Name:  pc
      [x] Auto-mount   [x] Make Permanent      → OK, OK
    Then run this again (if it still isn't there, restart the VM).
MSG
    exit 0
fi
share=${shares[0]}
if [ ${#shares[@]} -gt 1 ]; then
    say "Several shared folders (${shares[*]}); using $share (set SKILLBOT_SHARE to pick another)"
fi
if ! touch "$share/.skillbot-test" 2>/dev/null; then
    say "Can't write to $share: in Shared Folders Settings, untick Read-only, then restart the VM."
    exit 1
fi
rm -f "$share/.skillbot-test"

# 4. ~/share points at it; the panel's "Send to PC" and `python -m skillbot share` use it
ln -sfn "$share" "$HOME/share"
say "Shared folder ready: ~/share → $share
    Panel: Check → Send to PC   (or: python -m skillbot share)
    On the PC, look in the folder you picked → skillbot → the newest folder."
