import pytest

from skillbot.config import Step
from skillbot.game import BotError
from skillbot.planner import make_task

from fakes import BANK, LAYOUT, RANGE, TREE, blank, config, make_game, outline, put_item, slot_at

NEAR = (240, 150, 40, 30)      # next to the player (viewport center is 260,171)
FAR = (60, 40, 40, 30)


def gather_step(**kw):
    return dict(name="trees", skill="woodcutting", task="gather", target=TREE,
                items=["logs"], **kw)


def run_gather(fake, game, step_dict):
    task = make_task(game, Step.from_dict(step_dict))
    return task, task.run_batch()


class Trees:
    """Trees that give a log every 3 seconds while chopped; ``life`` maps a tree to how
    many logs it gives before it becomes a stump."""

    def __init__(self, fake, spots, life=None):
        self.fake, self.spots, self.life = fake, list(spots), dict(life or {})
        self.logs = {s: 0 for s in self.spots}
        self.alive = {s: True for s in self.spots}
        self.chopping, self.given, self.last = None, 0, 0.0
        for s in self.spots:
            outline(fake.img, *s, TREE)
        fake.on_click.append(self.click)
        fake.on_wait.append(self.tick)

    def click(self, fake, pt):
        for s in self.spots:
            x, y, w, h = s
            if self.alive[s] and x <= pt[0] < x + w and y <= pt[1] < y + h:
                self.chopping, self.last = s, fake.t

    def tick(self, fake):
        if not self.chopping or fake.t - self.last < 3:
            return
        self.last = fake.t
        free = [i for i in range(1, 28) if i not in fake.items()]
        if not free:
            return
        put_item(fake.img, free[0], "logs")
        self.given += 1
        self.logs[self.chopping] += 1
        if self.logs[self.chopping] == self.life.get(self.chopping):
            x, y, w, h = self.chopping
            fake.img[y:y + h, x:x + w] = (62, 53, 41)
            self.alive[self.chopping], self.chopping = False, None


def drop_on_shift_click(fake, pt):
    i = slot_at(pt)
    if fake.shift and i is not None:
        put_item(fake.img, i, None)


def test_gather_fills_inventory_then_drops():
    game, fake = make_game(config())
    Trees(fake, [NEAR])
    fake.on_click.append(drop_on_shift_click)
    task, result = run_gather(fake, game, gather_step(when_full="drop"))
    assert result == "ok"
    assert task.stats["items"] >= 26
    assert fake.items() == {}
    assert not any(shift and slot_at(p) == 0 for p, shift in fake.clicks)   # axe kept


def test_gather_moves_on_when_resource_depletes():
    game, fake = make_game(config())
    trees = Trees(fake, [NEAR, FAR], life={NEAR: 5})
    fake.on_click.append(drop_on_shift_click)
    run_gather(fake, game, gather_step(when_full="drop", idle_timeout=60))
    assert not trees.alive[NEAR] and trees.logs[FAR] >= 20
    far_clicks = [p for p, _ in fake.clicks if FAR[0] <= p[0] < FAR[0] + FAR[2]
                  and FAR[1] <= p[1] < FAR[1] + FAR[3]]
    assert far_clicks, "never switched to the second tree"
    # it switched well before the 60s idle timeout
    assert fake.t < 27 * 3 + 40


def test_gather_gives_up_when_nothing_is_gained():
    game, fake = make_game(config())
    outline(fake.img, *NEAR, TREE)
    with pytest.raises(BotError, match="without gaining"):
        run_gather(fake, game, gather_step(idle_timeout=5))


class Bank:
    def __init__(self, fake, withdraw=None):
        self.open = False
        self.withdraw = withdraw or {}     # bank slot -> (item, count)
        outline(fake.img, 380, 60, 30, 30, BANK)
        fake.on_click.append(self.click)
        fake.on_key.append(self.key)

    def click(self, fake, pt):
        if 380 <= pt[0] < 410 and 60 <= pt[1] < 90:
            self.open = True
            return
        if not self.open:
            return
        i = slot_at(pt)
        if i is not None and i in fake.items():
            name = fake.items()[i]
            for j, n in fake.items().items():     # quantity "All"
                if n == name:
                    put_item(fake.img, j, None)
        for b, (name, count) in self.withdraw.items():
            r = LAYOUT.bank_slot(b)
            if r.x <= pt[0] < r.x + r.w and r.y <= pt[1] < r.y + r.h:
                free = [k for k in range(1, 28) if k not in fake.items()][:count]
                for k in free:
                    put_item(fake.img, k, name)
                self.withdraw[b] = (name, 0)

    def key(self, fake, k):
        if k == "esc":
            self.open = False


def test_gather_banks_when_full():
    game, fake = make_game(config())
    Trees(fake, [NEAR])
    bank = Bank(fake)
    _, result = run_gather(fake, game, gather_step(when_full="bank"))
    assert result == "ok" and fake.items() == {} and not bank.open


class Range:
    """Cooks one raw shrimp every 2 seconds after use-item + range + space; a level-up
    after ``interrupt_after`` cooks stops the action."""

    def __init__(self, fake, interrupt_after=None):
        self.fake, self.selected, self.cooking, self.done = fake, False, False, 0
        self.interrupt_after, self.last = interrupt_after, 0.0
        outline(fake.img, 300, 140, 30, 30, RANGE)
        fake.on_click.append(self.click)
        fake.on_key.append(self.key)
        fake.on_wait.append(self.tick)

    def click(self, fake, pt):
        i = slot_at(pt)
        if i is not None:
            self.selected = fake.items().get(i) == "raw_shrimps"
        elif 300 <= pt[0] < 330 and 140 <= pt[1] < 170 and self.selected:
            self.menu = True

    def key(self, fake, k):
        if k == "space" and getattr(self, "menu", False):
            self.cooking, self.menu, self.last = True, False, fake.t

    def tick(self, fake):
        if not self.cooking or fake.t - self.last < 2:
            return
        self.last = fake.t
        raw = sorted(i for i, n in fake.items().items() if n == "raw_shrimps")
        if not raw:
            self.cooking = False
            return
        put_item(fake.img, raw[0], "shrimps")
        self.done += 1
        if self.interrupt_after and self.done == self.interrupt_after:
            self.cooking = False


def cook_step(**kw):
    return dict(name="cook", skill="cooking", task="process", target=RANGE,
                items=["raw_shrimps"], use_item="any", withdraw=[0], idle_timeout=6, **kw)


def test_process_cooks_everything_and_survives_level_up():
    game, fake = make_game(config())
    for i in range(1, 11):
        put_item(fake.img, i, "raw_shrimps")
    rng = Range(fake, interrupt_after=4)
    task = make_task(game, Step.from_dict(cook_step()))
    assert task.run_batch() == "ok"
    assert rng.done == 10
    assert set(fake.items().values()) == {"shrimps"}


def test_process_restocks_from_bank_then_reports_exhausted():
    game, fake = make_game(config())
    Bank(fake, withdraw={0: ("raw_shrimps", 5)})
    Range(fake)
    task = make_task(game, Step.from_dict(cook_step()))
    assert task.run_batch() == "ok"            # withdrew 5 raw and cooked them
    assert list(fake.items().values()).count("shrimps") == 5
    assert task.run_batch() == "exhausted"     # bank slot is empty now


def test_firemaking_lights_each_log():
    cfg = config()
    game, fake = make_game(cfg)
    start = (245, 160, 30, 20)
    outline(fake.img, *start, (128, 255, 128))
    for i in range(1, 6):
        put_item(fake.img, i, "logs")
    state = {"tinderbox": False}

    def click(fake, pt):
        i = slot_at(pt)
        if i == 0:
            state["tinderbox"] = True
        elif i is not None and state["tinderbox"] and fake.items().get(i) == "logs":
            put_item(fake.img, i, None)
            state["tinderbox"] = False
    fake.on_click.append(click)
    task = make_task(game, Step.from_dict(dict(
        name="fm", skill="firemaking", task="firemaking", target=(128, 255, 128),
        items=["logs"], idle_timeout=5)))
    assert task.run_batch() == "ok"
    assert task.stats["items"] == 5 and fake.items() == {}


def test_walks_route_tiles_until_target_visible():
    cfg = config(routes={"to_trees": [(255, 255, 255)]})
    game, fake = make_game(cfg)
    outline(fake.img, 100, 60, 30, 20, (255, 255, 255))

    def arrive(fake, pt):
        if 100 <= pt[0] < 130 and 60 <= pt[1] < 80:
            fake.img[:] = blank()
            outline(fake.img, *NEAR, TREE)
    fake.on_click.append(arrive)
    game.walk("to_trees", TREE)
    assert game.blobs(game.grab(), TREE)
