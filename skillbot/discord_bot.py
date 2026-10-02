"""The Discord service (`python -m skillbot discord`): delivers notifications and
questions to your channel, takes answers (buttons or replies), and gives you slash
commands from your phone. Only the Discord user in SKILLBOT_DISCORD_OWNER may use it.

Environment: SKILLBOT_DISCORD_TOKEN, SKILLBOT_DISCORD_CHANNEL (channel id),
SKILLBOT_DISCORD_OWNER (your user id). See docs/discord.md.
"""
import asyncio
import io
import logging
import os
from pathlib import Path

import discord
from discord import app_commands

from .discord_core import DiscordCore

log = logging.getLogger("skillbot")

MAX_BUTTONS = 20


def _env_int(name: str) -> int:
    value = os.environ.get(name, "").strip()
    if not value.isdigit():
        raise SystemExit(f"{name} must be set to a numeric Discord id (see docs/discord.md)")
    return int(value)


def screenshot_png() -> bytes:
    import cv2
    import mss
    import numpy as np
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        img = np.asarray(sct.grab(mon))[..., :3]
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


class AskButton(discord.ui.DynamicItem[discord.ui.Button], template=r"ask:(?P<ask>[\w-]+):(?P<idx>\d+)"):
    """A button answering a question. Its id survives restarts of the service."""

    core: DiscordCore = None
    owner_id: int = 0

    def __init__(self, ask_id: str, idx: int, label: str = "…"):
        super().__init__(discord.ui.Button(label=label[:80], custom_id=f"ask:{ask_id}:{idx}",
                                           style=discord.ButtonStyle.primary))
        self.ask_id, self.idx = ask_id, idx

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["ask"], int(match["idx"]), item.label or "…")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return
        text = self.core.answer_by_button(self.ask_id, self.idx)
        await interaction.response.edit_message(content=f"{interaction.message.content}\n**→ {text}**",
                                                view=None)


def run(data_dir: Path, summary_hour: int = 9) -> None:
    token = os.environ.get("SKILLBOT_DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("SKILLBOT_DISCORD_TOKEN is not set (see docs/discord.md)")
    channel_id = _env_int("SKILLBOT_DISCORD_CHANNEL")
    owner_id = _env_int("SKILLBOT_DISCORD_OWNER")
    core = DiscordCore(data_dir, summary_hour=summary_hour)
    AskButton.core, AskButton.owner_id = core, owner_id

    intents = discord.Intents.default()
    intents.message_content = True       # needed to read your replies to questions
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    async def allowed(interaction: discord.Interaction) -> bool:
        if interaction.user.id == owner_id:
            return True
        await interaction.response.send_message("Not allowed.", ephemeral=True)
        return False

    def simple(name: str, description: str):
        async def handler(interaction: discord.Interaction):
            if await allowed(interaction):
                text = await asyncio.to_thread(core.command, name)
                await interaction.response.send_message(text[:1900])
        tree.command(name=name, description=description)(handler)

    simple("status", "What the bot is doing")
    simple("levels", "Current levels")
    simple("pause", "Stop the bot so you can play")
    simple("resume", "Hand control back to the bot")
    simple("start", "Start the supervisor (RuneLite + bot)")
    simple("stop", "Stop the supervisor, RuneLite and the bot")
    simple("questions", "Open questions waiting for you")

    @tree.command(name="screenshot", description="What the VM's screen looks like right now")
    async def screenshot(interaction: discord.Interaction):
        if not await allowed(interaction):
            return
        await interaction.response.defer()
        png = await asyncio.to_thread(screenshot_png)
        await interaction.followup.send(file=discord.File(io.BytesIO(png), "screen.png"))

    async def deliver(channel) -> None:
        for msg in core.mailbox.pending():
            text = msg["text"][:1900]
            files = []
            if msg.get("image") and Path(msg["image"]).exists():
                files.append(discord.File(msg["image"]))
            if msg["kind"] == "ask":
                view = discord.ui.View(timeout=None)
                for i, option in enumerate(msg.get("options", [])[:MAX_BUTTONS]):
                    view.add_item(AskButton(msg["id"], i, option))
                hint = "\n*Tap an answer, or reply to this message with your own.*"
                sent = await channel.send(f"❓ {text}{hint}", view=view, files=files)
                core.remember_ask_message(sent.id, msg["id"])
            else:
                await channel.send(text, files=files)
            core.mailbox.delivered(msg["id"])

    async def background(channel) -> None:
        minute = 0
        while not client.is_closed():
            try:
                await deliver(channel)
                if minute % 12 == 0:                  # every ~60s
                    summary = await asyncio.to_thread(core.tick)
                    if summary:
                        await channel.send(summary)
            except discord.HTTPException as e:
                log.warning("Discord error, will retry: %s", e)
            minute += 1
            await asyncio.sleep(5)

    @client.event
    async def on_ready():
        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
        tree.copy_global_to(guild=channel.guild)
        await tree.sync(guild=channel.guild)     # guild commands show up immediately
        log.info("Discord connected as %s", client.user)
        if not getattr(client, "_started", False):
            client._started = True
            client.add_dynamic_items(AskButton)
            client.loop.create_task(background(channel))

    @client.event
    async def on_message(message: discord.Message):
        if message.author.id != owner_id or message.reference is None:
            return
        reply = core.answer_by_reply(message.reference.message_id, message.content)
        if reply:
            await message.reply(reply)

    client.run(token, log_handler=None)
