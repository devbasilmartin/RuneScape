"""Notifications: always the log; plus Discord, through the two-way Discord service's
mailbox when SKILLBOT_DISCORD_TOKEN is set (see docs/discord.md), or a plain webhook
when only SKILLBOT_DISCORD_WEBHOOK is set."""
import json
import logging
import os
import urllib.request
from pathlib import Path

log = logging.getLogger("skillbot")

_data_dir: Path | None = None
_tag: str | None = None


def setup(data_dir: Path, tag: str | None = None) -> None:
    """Called once at startup: where the (shared) mailbox is, and which profile we are."""
    global _data_dir, _tag
    _data_dir = Path(data_dir)
    _tag = tag


def notify(message: str, image: str | None = None) -> None:
    log.warning("NOTIFY: %s", message)
    if _tag:
        message = f"[{_tag}] {message}"
    if os.environ.get("SKILLBOT_DISCORD_TOKEN") and _data_dir is not None:
        from .messages import Mailbox
        Mailbox(_data_dir).post(message, image=image)
        return
    url = os.environ.get("SKILLBOT_DISCORD_WEBHOOK")
    if not url:
        return
    body = json.dumps({"content": f"[skillbot] {message}"[:1900]}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "skillbot"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except OSError as e:
        log.error("Discord notification failed: %s", e)
