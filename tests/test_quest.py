from skillbot.colors import Registry
from skillbot.config import Step
from skillbot.planner import make_task

from fakes import BG, LAYOUT, config, make_game, outline

REG = Registry.load()
TARGET, OPTION, ITEM = (REG.entries["quest_target"].rgb, REG.entries["quest_dialog"].rgb,
                        REG.entries["quest_item"].rgb)


class Quest:
    """talk to NPC → 2 continue pages → pick highlighted option (line 3) → use item on
    the altar → done (nothing highlighted)."""

    def __init__(self, fake):
        self.fake, self.stage, self.pages = fake, "npc", 0
        fake.on_click.append(self.click)
        fake.on_key.append(self.key)
        self.draw()

    def draw(self):
        img = self.fake.img
        img[:] = BG
        box = LAYOUT.chatbox
        img[box.y:box.y + box.h, box.x:box.x + box.w] = (200, 190, 150)
        if self.stage == "npc":
            outline(img, 240, 150, 30, 40, TARGET)
        elif self.stage == "talking":
            img[box.y + 100:box.y + 104, box.x + 150:box.x + 250] = (0, 0, 255)  # continue
        elif self.stage == "options":
            img[box.y + 60:box.y + 64, box.x + 120:box.x + 280] = OPTION        # line 3
        elif self.stage == "use item":
            s = LAYOUT.slot(4)
            outline(img, s.x + 2, s.y + 2, s.w - 4, s.h - 4, ITEM)
            outline(img, 320, 120, 40, 30, TARGET)

    def click(self, f, pt):
        box = LAYOUT.chatbox
        if self.stage == "npc" and 240 <= pt[0] < 270 and 150 <= pt[1] < 190:
            self.stage, self.pages = "talking", 2
        elif self.stage == "options" and box.y + 55 <= pt[1] < box.y + 70:
            self.stage = "use item"
        elif self.stage == "use item" and 320 <= pt[0] < 360 and 120 <= pt[1] < 150:
            self.stage = "done"
        self.draw()

    def key(self, f, k):
        if self.stage == "talking" and k == "space":
            self.pages -= 1
            if self.pages == 0:
                self.stage = "options"
            self.draw()


def test_follows_quest_helper_until_nothing_is_highlighted():
    game, fake = make_game(config())
    quest = Quest(fake)
    task = make_task(game, Step.from_dict(dict(name="Rune Mysteries", skill="attack",
                                                task="quest", idle_timeout=10)))
    assert task.run_batch() == "exhausted"          # finished: asks you to confirm
    assert quest.stage == "done" and task.stats["actions"] >= 5
