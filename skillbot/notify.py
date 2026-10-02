"""Notifications. For now: the log, plus a Discord webhook if SKILLBOT_DISCORD_WEBHOOK is
set. (The two-way Discord bot from the roadmap will replace this.)"""
import json
import logging
import os
import urllib.request

log = logging.getLogger("skillbot")


def notify(message: str) -> None:
    log.warning("NOTIFY: %s", message)
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
