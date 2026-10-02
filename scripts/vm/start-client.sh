#!/usr/bin/env bash
# Starts your RuneLite client. Set CLIENT_CMD in ~/.config/skillbot/env to the
# command your server's client uses, for example:
#   CLIENT_CMD="java -jar $HOME/client/RuneLite.jar"
#   CLIENT_CMD="$HOME/client/RuneLite.AppImage"
set -euo pipefail
ENV_FILE="$HOME/.config/skillbot/env"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
if [[ -z "${CLIENT_CMD:-}" ]]; then
    echo "Set CLIENT_CMD in $ENV_FILE first (see docs/vm-setup.md, step 7)." >&2
    exit 1
fi
# Software rendering is the reliable choice inside a VM.
export LIBGL_ALWAYS_SOFTWARE=1
exec $CLIENT_CMD
