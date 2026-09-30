from skillbot.config import Step
from skillbot.planner import make_task

from fakes import BG, LAYOUT, config, make_game, outline, put_item, slot_at

COW = (255, 128, 128)
LOOT = (128, 255, 255)
HP_COLOR = (255, 0, 0)


def draw_hp(img, frac):
    bar = LAYOUT.hp_bar
    img[bar.y:bar.y + bar.h, bar.x:bar.x + bar.w] = BG
    filled = int(round(bar.h * frac))
    if filled:
        img[bar.y + bar.h - filled:bar.y + bar.h, bar.x:bar.x + bar.w] = HP_COLOR


class Field:
    """Cows that die 6 seconds after being attacked, dropping bones and hide on their tile.
    Each fight costs the player 15% HP; food heals 40%."""

    def __init__(self, fake, cows, busy=()):
        self.fake, self.hp = fake, 1.0
        self.cows = {c: "idle" for c in cows}
        self.loot = {}
        self.fighting, self.started = None, 0.0
        self.log = []
        self.selected_spell = False
        for c in cows:
            outline(fake.img, *c, COW)
        for c in busy:
            self.cows[c] = "busy"
            self.bar(c)
        draw_hp(fake.img, self.hp)
        fake.on_click.append(self.click)
        fake.on_wait.append(self.tick)

    def bar(self, cow):
        x, y, w, _ = cow
        self.fake.img[y - 10:y - 7, x:x + w] = (0, 255, 0)

    def click(self, fake, pt):
        for c, state in self.cows.items():
            x, y, w, h = c
            if state == "idle" and x <= pt[0] < x + w and y <= pt[1] < y + h:
                self.cows[c], self.fighting, self.started = "fighting", c, fake.t
                self.log.append(("attack", c, self.selected_spell))
                self.selected_spell = False
                self.bar(c)
                return
        for tile, items in list(self.loot.items()):
            x, y, w, h = tile
            if x <= pt[0] < x + w and y <= pt[1] < y + h and items:
                free = [k for k in range(1, 28) if k not in fake.items()]
                put_item(fake.img, free[0], items.pop(0))
                if not items:
                    fake.img[y:y + h, x:x + w] = BG
                    del self.loot[tile]
                return
        i = slot_at(pt)
        if i is not None:
            name = fake.items().get(i)
            if name == "trout":
                self.hp = min(1.0, self.hp + 0.4)
                draw_hp(fake.img, self.hp)
                put_item(fake.img, i, None)
                self.log.append(("eat",))
            elif name == "bones":
                put_item(fake.img, i, None)
                self.log.append(("bury",))
        if tuple(pt) == (700, 400):          # the spell in the magic tab
            self.selected_spell = True

    def tick(self, fake):
        c = self.fighting
        if c is None or fake.t - self.started < 6:
            return
        x, y, w, h = c
        fake.img[y - 10:y + h, x:x + w] = BG
        self.cows[c], self.fighting = "dead", None
        tile = (x + 5, y + 5, 20, 20)
        outline(fake.img, *tile, LOOT)
        self.loot[tile] = ["bones", "cowhide"]
        self.hp = max(0.0, self.hp - 0.15)
        draw_hp(fake.img, self.hp)


COWS = [(230, 140, 40, 30), (320, 200, 40, 30), (150, 220, 40, 30), (380, 100, 40, 30)]


def combat_step(**kw):
    base = dict(name="cows", skill="strength", task="combat", target=COW, loot=LOOT,
                items=["cowhide"], food=["trout"], bury=["bones"], eat_below=0.5,
                kills_per_batch=3, idle_timeout=8)
    base.update(kw)
    return Step.from_dict(base)


def setup(cows=COWS, busy=(), food=3):
    cfg = config(hp_bar_color=HP_COLOR)
    game, fake = make_game(cfg)
    for i in range(1, 1 + food):
        put_item(fake.img, i, "trout")
    return game, fake, Field(fake, cows, busy)


def test_hp_bar_fraction():
    game, fake, _ = setup()
    task = make_task(game, combat_step())
    draw_hp(fake.img, 0.3)
    assert abs(task.hp(fake.img) - 0.3) < 0.02
    draw_hp(fake.img, 0)
    assert task.hp(fake.img) == 0


def test_kills_loots_buries_and_eats():
    game, fake, field = setup()
    task = make_task(game, combat_step(kills_per_batch=4))
    assert task.run_batch() == "ok"
    assert task.stats["kills"] == 4
    assert task.stats["buried"] >= 3
    assert ("eat",) in field.log            # 4 fights x 15% takes HP under 50%
    assert "cowhide" in fake.items().values()
    assert field.hp >= 0.4


def test_skips_enemies_already_in_combat():
    game, fake, field = setup(cows=COWS[:2], busy=[COWS[0]])
    task = make_task(game, combat_step(kills_per_batch=1))
    task.run_batch()
    attacked = [e[1] for e in field.log if e[0] == "attack"]
    assert attacked == [COWS[1]]


def test_out_of_food_stops_the_step():
    game, fake, field = setup(food=0)
    field.hp = 0.2
    draw_hp(fake.img, 0.2)
    task = make_task(game, combat_step(when_out_of_food="stop"))
    assert task.run_batch() == "exhausted"
    assert not any(e[0] == "attack" for e in field.log)


def test_magic_casts_the_spell_before_each_attack():
    game, fake, field = setup()
    task = make_task(game, combat_step(skill="magic", cast=[700, 400], kills_per_batch=2))
    task.run_batch()
    attacks = [e for e in field.log if e[0] == "attack"]
    assert attacks and all(spell for _, _, spell in attacks)
    assert fake.clicks[-1][0] != (700, 400)


def test_selects_attack_style_once():
    game, fake, field = setup()
    task = make_task(game, combat_step(style=2, kills_per_batch=2))
    task.run_batch()
    task.run_batch()
    points = [p for p, _ in fake.clicks]
    assert points.count(LAYOUT.combat_styles[2]) == 1
    assert points.index(LAYOUT.tabs["combat"]) < points.index(LAYOUT.combat_styles[2])


def test_ignores_loot_it_cannot_pick_up():
    game, fake, field = setup(cows=[])
    outline(fake.img, 250, 160, 20, 20, LOOT)       # a pile that never goes away
    task = make_task(game, combat_step())
    for _ in range(3):
        assert task.pick_up(fake.grab())
    assert not task.pick_up(fake.grab())
