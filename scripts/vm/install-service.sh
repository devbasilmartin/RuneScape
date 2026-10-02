#!/usr/bin/env bash
# Installs the supervisor as a systemd user service that starts with the desktop.
#   bash scripts/vm/install-service.sh            # install and start at every login
#   bash scripts/vm/install-service.sh --remove   # uninstall
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/skillbot.service"
AUTOSTART="$HOME/.config/autostart/skillbot.desktop"
ENV_FILE="$HOME/.config/skillbot/env"

if [[ "${1:-}" == "--remove" ]]; then
    systemctl --user stop skillbot.service 2>/dev/null || true
    rm -f "$UNIT" "$AUTOSTART"
    systemctl --user daemon-reload
    echo "removed"
    exit 0
fi

[[ -x "$REPO_DIR/.venv/bin/python" ]] || { echo "run scripts/vm/setup.sh first" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "create $ENV_FILE first (docs/vm-setup.md, step 7)" >&2; exit 1; }
chmod 600 "$ENV_FILE"     # it may hold your login and webhook

mkdir -p "$UNIT_DIR" "$(dirname "$AUTOSTART")"
cat > "$UNIT" <<UNIT
[Unit]
Description=skillbot supervisor (RuneLite + bot)
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$REPO_DIR/.venv/bin/python -m skillbot supervise
# Only a crash of the supervisor itself restarts it; when it gives up on purpose
# (too many restarts, or the bot stopped by itself) it exits 0 and stays stopped.
Restart=on-failure
RestartSec=60
UNIT

# Started from the desktop session so it gets the session's DISPLAY and XAUTHORITY.
cat > "$AUTOSTART" <<DESKTOP
[Desktop Entry]
Type=Application
Name=skillbot
Exec=sh -c 'sleep 20; systemctl --user import-environment DISPLAY XAUTHORITY; systemctl --user start skillbot.service'
X-GNOME-Autostart-enabled=true
NoDisplay=true
DESKTOP

systemctl --user daemon-reload
echo "installed. It starts 20s after every login."
echo "  start now:   systemctl --user start skillbot"
echo "  stop:        systemctl --user stop skillbot"
echo "  status/logs: systemctl --user status skillbot; tail -f $REPO_DIR/data/supervisor.log"
