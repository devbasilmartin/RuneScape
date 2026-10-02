import pytest

from skillbot.dialog import Dialog
from skillbot.game import BotError
from skillbot.navigation import Destinations, Hub, Navigator

from fakes import BG, LAYOUT, TREE, config, make_game, outline, put_item, slot_at

PATH = (255, 0, 128)
MARKER = (192, 192, 0)
EXTRA = {"varrock_teleport": (0, 192, 255)}


class World:
    """Teleport with a tablet → hub; the world map; "Set target" draws a path on the
    minimap that gets shorter with each minimap click until the trees are in sight."""

    def __init__(self, fake, strides=4, menu_option=1, offset=(40, -30)):
        self.fake, self.place, self.map_open = fake, "lumbridge", False
        self.menu_at, self.target_set, self.left = None, False, strides
        self.menu_option, self.offset = menu_option, offset
        fake.on_click.append(self.click)
        fake.on_key.append(lambda f, k: self.close() if k == "esc" else None)
        orig = fake.click

        def click(pt, button="left"):
            if button == "right" and self.map_open:
                self.menu_at = tuple(pt)
            orig(pt, button)
        fake.click = click

    def close(self):
        self.map_open = False
        self.draw()

    def draw(self):
        img = self.fake.img
        img[:LAYOUT.viewport.y + LAYOUT.viewport.h, :LAYOUT.viewport.x + LAYOUT.viewport.w] = BG
        mx, my = LAYOUT.minimap_center
        img[my - 70:my + 70, mx - 70:mx + 70] = BG
        if self.place == "varrock":
            outline(img, 250, 160, 20, 20, MARKER)
        if self.target_set and self.left > 0:
            length = min(10 + 12 * self.left, 120)   # path pixels heading north-east
            for t in range(length):
                img[my - t // 2, mx + t // 2] = PATH
        if self.place == "trees":
            outline(img, 240, 150, 40, 30, TREE)

    def click(self, fake, pt):
        i = slot_at(pt)
        if i is not None and fake.items().get(i) == "varrock_teleport":
            put_item(fake.img, i, None)
            self.place = "varrock"
            self.draw()
            return
        if tuple(pt) == LAYOUT.world_map_button:
            self.map_open = True
            return
        if self.map_open and self.menu_at:
            lay = LAYOUT
            expected = (self.menu_at[0], self.menu_at[1] + lay.menu_header
                        + lay.menu_row * (self.menu_option - 1) + lay.menu_row // 2)
            cx, cy = lay.world_map_center
            if tuple(pt) == expected and self.menu_at == (cx + self.offset[0], cy + self.offset[1]):
                self.target_set = True
            self.menu_at = None
            return
        mx, my = LAYOUT.minimap_center
        if self.target_set and abs(pt[0] - mx) < 70 and abs(pt[1] - my) < 70:
            self.left -= 1
            if self.left == 0:
                self.place = "trees"
            self.draw()


def setup(strides=4, with_tablet=True):
    import fakes
    cfg = config(extra_items=EXTRA)
    game, fake = make_game(cfg)
    fake.items = lambda: game.inv.tags(fake.img)
    fakes.ITEMS.update(EXTRA)
    if with_tablet:
        put_item(fake.img, 3, "varrock_teleport")
    world = World(fake, strides=strides)
    world.draw()
    hubs = {"varrock": Hub.from_dict("varrock", {"teleport": {"item": "varrock_teleport"},
                                                  "marker": MARKER})}
    dests = Destinations(None, {"varrock trees": {"hub": "varrock", "offset": [40, -30]}})
    game.nav = Navigator(game, hubs, dests, PATH, stride_wait=(3, 3))
    return game, fake, world


@pytest.fixture(autouse=True)
def restore_items():
    import fakes
    before = dict(fakes.ITEMS)
    yield
    fakes.ITEMS.clear()
    fakes.ITEMS.update(before)


def test_travel_teleports_sets_target_and_follows_path():
    game, fake, world = setup(strides=4)
    game.nav.travel("varrock trees", TREE)
    assert world.place == "trees" and world.target_set
    assert game.blobs(game.grab(), TREE)
    assert "varrock_teleport" not in fake.items().values()     # the tablet was used


def test_no_travel_when_already_there():
    game, fake, world = setup()
    world.place = "trees"
    world.draw()
    game.nav.travel("varrock trees", TREE)
    assert fake.clicks == []


def test_out_of_tablets_is_reported():
    game, fake, world = setup(with_tablet=False)
    with pytest.raises(BotError, match="no varrock_teleport"):
        game.nav.travel("varrock trees", TREE)
    assert game.reported


def test_unknown_destination_explains_how_to_add_it():
    game, _, _ = setup()
    with pytest.raises(BotError, match="add-destination"):
        game.nav.travel("lumbridge swamp", TREE)


def test_stuck_on_a_path_that_never_shortens():
    game, fake, world = setup(strides=10 ** 6)
    world.click = lambda f, pt: None                    # clicks do nothing: a closed door
    fake.on_click[:] = [world.click]
    world.target_set = True
    world.place = "varrock"
    world.draw()
    with pytest.raises(BotError, match="stuck"):
        game.nav.follow(TREE)


def test_menu_point_rows():
    game, _, _ = setup()
    lay = LAYOUT
    assert game.nav.menu_point((100, 100), 1) == (100, 100 + lay.menu_header + lay.menu_row // 2)
    assert game.nav.menu_point((100, 100), 3)[1] == 100 + lay.menu_header + 2 * lay.menu_row \
        + lay.menu_row // 2


def test_dialog_continues_and_chooses():
    cfg = config()
    game, fake = make_game(cfg)
    pages = [3]

    def draw():
        box = LAYOUT.chatbox
        fake.img[box.y:box.y + box.h, box.x:box.x + box.w] = (200, 190, 150)
        if pages[0] > 0:
            fake.img[box.y + 100:box.y + 104, box.x + 150:box.x + 250] = (0, 0, 255)
    draw()
    fake.on_key.append(lambda f, k: (pages.__setitem__(0, pages[0] - 1), draw())
                       if k == "space" else None)
    d = Dialog(game)
    assert d.waiting(fake.grab())
    assert d.advance() == 3 and not d.waiting(fake.grab())
    d.choose(2)
    assert fake.keys[-1] == "2"


def test_planner_travels_to_a_step_location_first(monkeypatch):
    from skillbot.config import Step
    from skillbot.planner import TASK_TYPES, Planner
    from skillbot.tasks import Task

    class Done(Task):
        def run_batch(self):
            return "exhausted"
    monkeypatch.setitem(TASK_TYPES, "gather", Done)
    game, fake, world = setup()
    calls = []
    game.nav.travel = lambda dest, until: calls.append((dest, until))
    levels = type("L", (), {"get": lambda self, s: 1, "refresh": lambda self, s: None,
                            "reader": type("R", (), {"complete": lambda self: True})()})()
    step = Step.from_dict(dict(name="t", skill="woodcutting", task="gather", target=TREE,
                               items=["logs"], location="varrock trees"))
    Planner(game, levels).run_step(step)
    assert calls == [("varrock trees", TREE)]


def test_hub_only_destination_just_teleports():
    game, fake, world = setup()
    world.place = "varrock"
    calls = []
    game.nav.teleport = lambda hub: (calls.append(hub), world.draw())
    game.nav.travel("hub:varrock", MARKER)
    assert calls == ["varrock"]
