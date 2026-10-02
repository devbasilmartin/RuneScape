"""Semi-automatic Slayer (docs/slayer.md).

The bot can't read the chat, so you name the monster: when it has no task it travels to
a Slayer master, asks for an assignment, and asks you on Discord (or `skillbot
slayer-task`) which monster it got. While it waits the planner trains other steps. Once
you answer, it travels to the monster's location and fights it until RuneLite's Slayer
plugin infobox disappears, which happens when the task is finished.

    no task -> master -> ask you -> (other steps) -> fight -> infobox gone -> no task ...

Your answer can also be "skip" (get a new task from Turael; this resets your streak) or
"mine" (you do this one; the bot waits for the infobox to disappear).

State survives restarts in data/slayer.json. The remaining kill count is read from the
infobox with learned digits (`skillbot learn-slayer`) for progress reports only; the end
of the task is the infobox disappearing.
"""
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import yaml

from .colors import Registry, resolve_config
from .config import Step
from .digits import GlyphBook, segment
from .game import BotError
from .tasks import Task

log = logging.getLogger("skillbot")

REPO_DIR = Path(__file__).resolve().parent.parent
SLAYER_FILE = REPO_DIR / "library" / "slayer" / "slayer.yaml"
SKIP, MINE = "skip (Turael)", "mine"
GONE_LOOKS = 3          # looks without the infobox before the task counts as finished


@dataclass
class Master:
    id: str
    name: str
    location: str
    combat: int = 3
    option: int = 2
    slayer: int = 1
    quests: tuple = ()


@dataclass
class Monster:
    id: str
    name: str
    location: str | None = None
    aliases: tuple = ()
    step: dict = field(default_factory=dict)


class SlayerBook:
    def __init__(self, masters: dict[str, Master], monsters: dict[str, Monster]):
        self.masters = masters
        self.monsters = monsters

    @classmethod
    def load(cls, path: Path | None = None) -> "SlayerBook":
        data = yaml.safe_load(Path(path or SLAYER_FILE).read_text()) or {}
        masters = {k: Master(k, **{**v, "quests": tuple(v.get("quests", ()))})
                   for k, v in (data.get("masters") or {}).items()}
        monsters = {k: Monster(k, **{**v, "aliases": tuple(v.get("aliases", ()))})
                    for k, v in (data.get("monsters") or {}).items()}
        return cls(masters, monsters)

    def match(self, text: str) -> str | None:
        """The monster id for an answer such as "Hill giants" or "hill_giants"."""
        t = " ".join(text.lower().replace("_", " ").split())
        for mid, m in self.monsters.items():
            names = {mid.replace("_", " "), m.name.lower(), *(a.lower() for a in m.aliases)}
            if t in names or t.rstrip("s") in names:
                return mid
        return None

    def master_for(self, levels: dict, quests) -> Master:
        best = None
        for m in self.masters.values():
            if (combat_level(levels) >= m.combat and levels.get("slayer", 1) >= m.slayer
                    and all(quests.has(q) for q in m.quests)):
                best = m
        return best or next(iter(self.masters.values()))


def combat_level(levels: dict) -> int:
    lv = lambda s: levels.get(s, 10 if s == "hitpoints" else 1)   # noqa: E731
    base = 0.25 * (lv("defence") + lv("hitpoints") + lv("prayer") // 2)
    melee = 0.325 * (lv("attack") + lv("strength"))
    ranged = 0.325 * (lv("ranged") * 3 // 2)
    magic = 0.325 * (lv("magic") * 3 // 2)
    return int(base + max(melee, ranged, magic))


def infobox_mask(img) -> np.ndarray:
    """Infobox numbers are white text with a black shadow."""
    rgb = img[..., :3]
    return (rgb.min(axis=-1) > 220)


def infobox_glyphs(layout, img):
    return segment(infobox_mask(layout.slayer_box.crop(img)))


class SlayerState:
    def __init__(self, path: Path):
        self.path = path
        data = json.loads(path.read_text()) if path.exists() else {}
        self.state = data.get("state", "need_task")   # need_task | asking | assigned | mine
        self.master = data.get("master")
        self.monster = data.get("monster")
        self.ask_id = data.get("ask_id")
        self.left = data.get("left")
        self.done = data.get("done", 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({k: getattr(self, k) for k in (
            "state", "master", "monster", "ask_id", "left", "done")}, indent=1))


def mailbox():
    """The Discord mailbox (shared between profiles), as notify.py uses it."""
    from . import notify
    from .messages import Mailbox
    return Mailbox(notify._data_dir) if notify._data_dir is not None else None


def ask_key(tag=None) -> str:
    from . import notify
    tag = notify._tag if tag is None else tag
    return f"slayer:{tag or ''}"


class SlayerTask(Task):
    def __init__(self, game, step, book: SlayerBook | None = None, levels: dict | None = None):
        super().__init__(game, step)
        cfg = game.cfg
        self.book = book or SlayerBook.load()
        self.registry = Registry.load(cfg.colors_file)
        self.master_color = self.registry.resolve("slayer_master")
        self.state = SlayerState(cfg.data_dir / "slayer.json")
        self.digits = GlyphBook.load(cfg.data_dir / "slayer_digits.json")
        self.levels = levels
        self.inner = None           # the combat task for the current monster
        self.gone = 0
        self.stats.update(tasks=self.state.done)

    # ---- the infobox -------------------------------------------------------------------
    def glyphs(self, img):
        return infobox_glyphs(self.game.layout, img)

    def present(self, img) -> bool:
        return bool(self.glyphs(img))

    def read_left(self, img) -> int | None:
        glyphs, prev = self.glyphs(img), self.state.left
        if prev is None:
            return self.digits.read(glyphs)
        value = self.digits.read_among(glyphs, range(max(0, prev - 10), prev + 1))
        if value is not None and value != prev:
            self.digits.save()
        return value

    def finished(self) -> bool:
        """The infobox has been gone for a few looks in a row."""
        g = self.game
        for _ in range(GONE_LOOKS):
            img = g.grab()
            if self.present(img):
                self.gone = 0
                return False
            self.gone += 1
            if self.gone >= GONE_LOOKS:
                return True
            g.wait(1.5, 2.5)
        return False

    # ---- masters and questions ---------------------------------------------------------
    def levels_now(self) -> dict:
        if self.levels is not None:
            return self.levels
        path = self.game.cfg.data_dir / "progress.json"
        return json.loads(path.read_text()).get("levels", {}) if path.exists() else {}

    def pick_master(self) -> Master:
        from .goals import QuestLog
        wanted = self.step.vars.get("master")
        if wanted:
            if wanted not in self.book.masters:
                raise BotError(f"unknown Slayer master {wanted!r} (see {SLAYER_FILE.name})")
            return self.book.masters[wanted]
        quests = QuestLog(self.game.cfg.data_dir / "quests.json")
        return self.book.master_for(self.levels_now(), quests)

    def get_assignment(self, master: Master) -> None:
        g = self.game
        img = g.grab()
        if not g.blobs(img, self.master_color) and getattr(g, "nav", None) is not None:
            g.nav.travel(master.location, self.master_color)
            img = g.grab()
        blob = g.nearest(img, self.master_color)
        if blob is None:
            raise BotError(f"can't see {master.name} (NPC Indicators: slayer_master)")
        from .dialog import Dialog
        lay = g.layout
        g.controls.click(blob.center, button="right")
        g.wait(0.4, 0.6)
        g.controls.click((blob.center[0], blob.center[1] + lay.menu_header
                          + lay.menu_row * (master.option - 1) + lay.menu_row // 2))
        if not g.wait_until(lambda im: Dialog(g).waiting(im) or self.present(im), 15):
            raise BotError(f"{master.name} didn't answer the Assignment option")
        Dialog(g).advance()
        if not g.wait_until(self.present, 10):
            raise BotError(f"no Slayer infobox after asking {master.name} for a task "
                           "(is the Slayer plugin's infobox on, and layout.slayer_box right?)")
        self.state.master = master.id
        log.info("slayer: new task from %s", master.name)

    def ask(self, why: str) -> None:
        box = mailbox()
        options = [m.name for m in self.book.monsters.values()] + [SKIP, MINE]
        question = (f"{why} Which monster? Reply with its name, \"skip\" for a new task "
                    f"from Turael (resets your streak), or \"mine\" to do it yourself.")
        from . import notify
        if notify._tag:
            question = f"[{notify._tag}] {question}"
        st = self.state
        st.ask_id = box.ask(question, options, key=ask_key()) if box else None
        st.state, st.monster, st.left = "asking", None, None
        st.save()
        if box is None:
            from .notify import notify as send
            send(f"{why} Tell me which monster with `python -m skillbot slayer-task NAME`.")

    def answer(self) -> str | None:
        st = self.state
        if st.ask_id is None:
            return None
        box = mailbox()
        return box.answer(st.ask_id) if box else None

    # ---- fighting ----------------------------------------------------------------------
    def monster_step(self, monster: Monster) -> Step:
        raw = {"name": f"slayer: {monster.name}", "skill": self.step.skill, "task": "combat",
               "target": "enemy", **monster.step}
        raw = resolve_config({"plan": [raw]}, self.registry)["plan"][0]
        parsed = Step.from_dict(raw)
        over = {k: getattr(parsed, k) for k in monster.step}
        return replace(self.step, name=parsed.name, task=parsed.task,
                       location=monster.location, target=parsed.target, **{
                           k: v for k, v in over.items() if k not in ("target", "task")})

    def fight(self) -> str:
        from .planner import make_task
        g, st = self.game, self.state
        monster = self.book.monsters[st.monster]
        if self.inner is None or self.inner.step.name != f"slayer: {monster.name}":
            step = self.monster_step(monster)
            self.inner = make_task(g, step)
            self.inner.on_progress = self.on_progress
            if monster.location and getattr(g, "nav", None) is not None \
                    and not g.blobs(g.grab(), step.target):
                g.nav.travel(monster.location, step.target)
        result = self.inner.run_batch()
        self.stats["kills"] = self.inner.stats.get("kills", 0)
        left = self.read_left(g.grab())
        if left is not None:
            st.left = self.stats["left"] = left
            st.save()
        return result

    # ---- the cycle ---------------------------------------------------------------------
    def run_batch(self) -> str:
        g, st = self.game, self.state
        from .notify import notify
        if st.state in ("assigned", "mine") and self.finished():
            if st.state == "assigned":
                st.done += 1
                self.stats["tasks"] = st.done
                notify(f"Slayer task done: {self.book.monsters[st.monster].name} "
                       f"({st.done} tasks so far)")
            st.state, st.monster, st.left, self.inner = "need_task", None, None, None
            st.save()
        if st.state == "assigned":
            self.stats["batches"] += 1
            return self.fight()
        if st.state == "mine":
            return "exhausted"              # yours; train something else meanwhile
        if st.state == "asking":
            return self.handle(self.answer())
        # need_task
        if self.present(g.grab()):
            self.ask("There's already a Slayer task running.")
            return "exhausted"
        master = self.pick_master()
        self.get_assignment(master)
        self.ask(f"New Slayer task from {master.name}.")
        return "exhausted"

    def handle(self, answer: str | None) -> str:
        st = self.state
        if answer is None:
            return "exhausted"
        text = answer.strip().lower()
        from .notify import notify
        if text == MINE or text.startswith("mine"):
            st.state, st.ask_id = "mine", None
            st.save()
            notify("OK, that Slayer task is yours; I'll get the next one once its "
                   "infobox is gone.")
            return "exhausted"
        if text.startswith("skip"):
            st.ask_id = None
            self.get_assignment(self.book.masters["turael"])
            self.ask("Skipped with Turael; new task.")
            return "exhausted"
        monster = self.book.match(answer)
        if monster is None:
            st.ask_id = None
            self.ask(f"I don't know {answer!r} yet.")
            return "exhausted"
        st.state, st.monster, st.ask_id = "assigned", monster, None
        st.save()
        notify(f"Slayer: going for {self.book.monsters[monster].name}.")
        log.info("slayer: task is %s", monster)
        self.stats["batches"] += 1
        return self.fight()


def answer_from_cli(data_dir: Path, mailbox_dir: Path, text: str, tag=None,
                    book: SlayerBook | None = None) -> str:
    """`skillbot slayer-task NAME`: answer the open question, or set the task directly."""
    from .messages import Mailbox
    book = book or SlayerBook.load()
    if text.lower() not in (MINE,) and not text.lower().startswith(("skip", "mine")) \
            and book.match(text) is None:
        names = ", ".join(m.name for m in book.monsters.values())
        raise ValueError(f"unknown monster {text!r}; known: {names}, skip, mine")
    box = Mailbox(mailbox_dir)
    for ask in box.open_asks():
        if ask.get("key") == ask_key(tag):
            box.reply(ask["id"], text)
            return "answered the bot's question"
    st = SlayerState(Path(data_dir) / "slayer.json")
    if text.lower().startswith("mine"):
        st.state, st.monster = "mine", None
    elif text.lower().startswith("skip"):
        raise ValueError("skip only answers an open question (the bot isn't asking)")
    else:
        st.state, st.monster = "assigned", book.match(text)
    st.ask_id, st.left = None, None
    st.save()
    return f"set the current Slayer task: {st.monster or 'yours'}"
