import pytest

from skillbot import notify
from skillbot.colors import Registry
from skillbot.config import Step
from skillbot.messages import Mailbox
from skillbot.planner import make_task
from skillbot.slayer import (SlayerBook, SlayerState, answer_from_cli, ask_key,
                             combat_level)

from fakes import BG, LAYOUT, config, draw_number, make_game, outline

REG = Registry.load()
MASTER = REG.entries["slayer_master"].rgb
STEP = dict(name="slayer", skill="slayer", task="slayer", food=["trout"],
            vars={"master": "vannaka"})


class Master:
    """Right-click the master → Assignment (row 2) → one continue page → infobox."""

    def __init__(self, fake, count=12):
        self.fake, self.count, self.stage = fake, count, "idle"
        outline(fake.img, 240, 150, 20, 40, MASTER)
        fake.on_click.append(self.click)
        fake.on_key.append(self.key)

    def click(self, f, pt):
        if self.stage == "idle" and f.right_clicks:
            rx, ry = f.right_clicks[-1]
            row = (pt[1] - ry - LAYOUT.menu_header) // LAYOUT.menu_row + 1
            if row == 2:
                self.stage = "talking"
                box = LAYOUT.chatbox
                f.img[box.y + 100:box.y + 104, box.x + 150:box.x + 250] = (0, 0, 255)

    def key(self, f, k):
        if self.stage == "talking" and k == "space":
            box = LAYOUT.chatbox
            f.img[box.y + 100:box.y + 104, box.x + 150:box.x + 250] = BG
            self.stage = "assigned"
            self.draw()

    def draw(self):
        b = LAYOUT.slayer_box
        self.fake.img[b.y:b.y + b.h, b.x:b.x + b.w] = BG
        if self.count > 0:
            draw_number(self.fake.img, b.x + 2, b.y + 3, self.count, (255, 255, 255))


@pytest.fixture
def mail(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "_data_dir", tmp_path / "shared")
    monkeypatch.setattr(notify, "_tag", None)
    return Mailbox(tmp_path / "shared")


def test_gets_a_task_asks_you_fights_it_then_starts_over(tmp_path, mail):
    game, fake = make_game(config(data_dir=tmp_path))
    master = Master(fake)
    task = make_task(game, Step.from_dict(STEP))

    assert task.run_batch() == "exhausted"          # assigned; now waits for you
    assert master.stage == "assigned"
    (ask,) = mail.open_asks()
    assert "Vannaka" in ask["question"] and "Hill giants" in ask["options"]
    assert task.run_batch() == "exhausted"          # still no answer: train something else

    mail.reply(ask["id"], "hill giant")
    fights = []

    def fight():                                    # stands in for the combat task
        fights.append(task.state.monster)
        master.count -= 4
        master.draw()
        return "ok"
    task.fight = fight
    assert task.run_batch() == "ok"
    assert SlayerState(tmp_path / "slayer.json").monster == "hill_giants"
    while master.count > 0:
        assert task.run_batch() == "ok"
    assert fights == ["hill_giants"] * 3

    master.stage, master.count = "idle", 20          # infobox gone: back to the master
    assert task.run_batch() == "exhausted"
    assert task.state.done == 1 and task.state.state == "asking"
    assert master.stage == "assigned"


def test_unknown_answer_asks_again_and_mine_waits(tmp_path, mail):
    game, fake = make_game(config(data_dir=tmp_path))
    master = Master(fake)
    task = make_task(game, Step.from_dict(STEP))
    task.run_batch()
    (ask,) = mail.open_asks()
    mail.reply(ask["id"], "abyssal demons")
    assert task.run_batch() == "exhausted"
    (ask,) = mail.open_asks()
    assert "don't know" in ask["question"]
    mail.reply(ask["id"], "mine")
    assert task.run_batch() == "exhausted" and task.state.state == "mine"
    master.count = 0
    master.draw()                                    # you finished it
    master.stage, master.count = "idle", 5
    assert task.run_batch() == "exhausted"
    assert task.state.state == "asking" and task.state.done == 0


def test_master_must_answer_with_an_infobox(tmp_path, mail):
    from skillbot.game import BotError
    game, fake = make_game(config(data_dir=tmp_path))
    outline(fake.img, 240, 150, 20, 40, MASTER)      # nobody answers the menu
    task = make_task(game, Step.from_dict(STEP))
    with pytest.raises(BotError, match="didn't answer"):
        task.run_batch()


def test_monster_step_takes_the_slayer_steps_supplies(tmp_path):
    game, _ = make_game(config(data_dir=tmp_path))
    task = make_task(game, Step.from_dict(STEP))
    step = task.monster_step(task.book.monsters["hill_giants"])
    assert step.task == "combat" and step.food == ("trout",)
    assert step.location == "edgeville hill giants"
    assert step.target == REG.resolve("enemy")


def test_book_matching_masters_and_combat_level():
    book = SlayerBook.load()
    assert book.match("Hill Giants") == book.match("hill_giants") == "hill_giants"
    assert book.match("chicken") == "birds" and book.match("dragons") is None
    assert combat_level({}) == 3
    assert combat_level({"attack": 60, "strength": 60, "defence": 60, "hitpoints": 60,
                         "prayer": 43}) == 74

    class Quests:
        def __init__(self, done):
            self.done = done

        def has(self, q):
            return q in self.done
    strong = {s: 65 for s in ("attack", "strength", "defence", "hitpoints")}
    assert book.master_for({}, Quests([])).id == "turael"
    assert book.master_for(strong, Quests([])).id == "vannaka"
    assert book.master_for(strong, Quests(["Lost City"])).id == "chaeldar"


def test_cli_answers_the_open_question_or_sets_the_task(tmp_path):
    box = Mailbox(tmp_path)
    ask_id = box.ask("which?", ["Cows"], key=ask_key("main"))
    assert "answered" in answer_from_cli(tmp_path, tmp_path, "cows", tag="main")
    assert box.answer(ask_id) == "cows"
    assert "cows" in answer_from_cli(tmp_path, tmp_path, "cow", tag="main")   # nothing open
    assert SlayerState(tmp_path / "slayer.json").monster == "cows"
    with pytest.raises(ValueError, match="unknown monster"):
        answer_from_cli(tmp_path, tmp_path, "dragons", tag="main")
