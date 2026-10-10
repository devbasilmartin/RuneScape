import cv2
import numpy as np
import pytest

from skillbot.config import Step
from skillbot.layout import Rect
from skillbot.mouse import MouseConfig, MouseLab, format_summary, summary_rows
from skillbot.planner import make_task
from skillbot.vision import find_blobs, outline_polygon

from fakes import BG, TREE, config, make_game, put_item, slot_at

experiment = pytest.importorskip("humanized_input.experiment")
bridge_mod = pytest.importorskip("humanized_input.bridge")
Shape = experiment.Shape


def l_mask():
    m = np.zeros((80, 80), bool)
    m[10:70, 10:25] = True
    m[55:70, 10:70] = True
    return m


def ring_mask():
    m = np.zeros((80, 80), np.uint8)
    cv2.circle(m, (40, 40), 30, 1, -1)
    cv2.circle(m, (40, 40), 15, 0, -1)
    return m.astype(bool)


def test_filled_l_keeps_its_notch():
    shape = Shape.polygon(outline_polygon(l_mask()))
    assert not shape.contains(*shape.box.center)          # the box centre misses the L
    x, y = shape.deepest()
    assert l_mask()[int(y), int(x)]


def test_ring_keeps_its_hole():
    shape = Shape.polygon(outline_polygon(ring_mask()))
    assert not shape.contains(40, 40)                      # the hole
    assert shape.contains(40, 15) and shape.contains(65, 40)
    x, y = shape.deepest()
    assert ring_mask()[int(y), int(x)]


def test_thin_outline_counts_as_filled_but_follows_the_silhouette():
    m = np.zeros((80, 80), np.uint8)
    pts = np.array([[10, 10], [24, 10], [24, 55], [69, 55], [69, 69], [10, 69]], np.int32)
    cv2.polylines(m, [pts], True, 1, 2)
    shape = Shape.polygon(outline_polygon(m.astype(bool)))
    assert shape.contains(17, 40) and shape.contains(50, 62)    # inside the outline
    assert not shape.contains(45, 30)                           # the notch
    gappy = m.copy()
    gappy[30:33, :] = 0                                         # occluded: a small gap
    assert Shape.polygon(outline_polygon(gappy.astype(bool))).contains(17, 40)


def test_blobs_carry_polygons_in_canvas_coordinates():
    img = np.full((200, 300, 3), BG, np.uint8)
    img[60:120, 110:125] = TREE
    img[105:120, 110:170] = TREE
    (blob,) = find_blobs(img, TREE, 10, region=Rect(100, 50, 150, 100))
    shape = Shape.polygon(blob.polygon)
    assert shape.contains(117, 70) and shape.contains(160, 112)
    assert not shape.contains(150, 80)
    assert blob.polygon == find_blobs(img, TREE, 10)[0].polygon


def test_controls_play_converts_and_presses():
    from skillbot.controls import Controls

    class PG:
        def __init__(self):
            self.log = []

        def moveTo(self, x, y, duration):
            self.log.append(("move", x, y, duration))

        def mouseDown(self, button):
            self.log.append(("down", button))

        def mouseUp(self, button):
            self.log.append(("up", button))

    class Scr:
        def to_screen(self, pt):
            return pt[0] + 100, pt[1] + 50

    c = Controls.__new__(Controls)
    c._pg, c.screen = PG(), Scr()
    slept = []
    events, _ = experiment.plan(experiment.MouseStyle("t", path="linear", aim="deepest"),
                                (0, 0), Shape.rect(40, 40, 20, 20), seed=1)
    c.play([{"type": e.kind, "x": e.x, "y": e.y, "delay": e.delay_before, "button": e.button}
            for e in events], sleep=slept.append)
    assert c._pg.log[-2:] == [("down", "left"), ("up", "left")]
    assert c._pg.log[-3][:3] == ("move", 150, 100)              # aim (50, 50) + origin
    assert all(m[3] == 0 for m in c._pg.log if m[0] == "move")
    assert len(slept) == sum(1 for e in events if e.delay_before > 0)


def test_mouse_config_defaults_off():
    assert MouseConfig.from_dict(None).enabled is False
    with pytest.raises(ValueError):
        MouseConfig.from_dict({"pick": "best"})
    with pytest.raises(ValueError):
        config(mouse={"enabeld": True})


class LTree:
    """An L-shaped tree highlight: only clicks on the L itself start chopping."""

    def __init__(self, fake):
        self.fake, self.chopping, self.last = fake, False, 0.0
        self.mask = np.zeros(fake.img.shape[:2], bool)
        self.mask[140:190, 230:242] = True
        self.mask[178:190, 230:290] = True
        fake.img[self.mask] = TREE
        fake.on_click.append(self.click)
        fake.on_wait.append(self.tick)

    def click(self, fake, pt):
        x, y = int(pt[0]), int(pt[1])
        if 0 <= y < self.mask.shape[0] and 0 <= x < self.mask.shape[1] and self.mask[y, x]:
            self.chopping, self.last = True, fake.t
        i = slot_at(pt)
        if fake.shift and i is not None:
            put_item(fake.img, i, None)

    def tick(self, fake):
        if self.chopping and fake.t - self.last >= 3:
            self.last = fake.t
            free = [i for i in range(1, 28) if i not in fake.items()]
            if free:
                put_item(fake.img, free[0], "logs")


def test_ab_testing_logs_which_style_lands(tmp_path):
    styles = tmp_path / "styles.yaml"
    styles.write_text("styles:\n  - {name: box-centre, path: instant, aim: center}\n"
                      "  - {name: deepest, path: instant, aim: deepest}\n")
    game, fake = make_game(config())
    game.mouse = MouseLab.load(MouseConfig(enabled=True, styles="styles.yaml"), tmp_path,
                               tmp_path)
    game.mouse.activity = "L trees"
    LTree(fake)
    task = make_task(game, Step.from_dict(dict(name="L trees", skill="woodcutting",
                                               task="gather", target=TREE, items=["logs"],
                                               when_full="drop", idle_timeout=10)))
    assert task.run_batch() == "ok"
    rows = {(r["step"], r["style"]): r for r in summary_rows(tmp_path / "mouse_outcomes.jsonl")}
    assert rows[("L trees", "box-centre")]["rate"] == 0.0
    assert rows[("L trees", "deepest")]["rate"] == 1.0
    assert "deepest" in format_summary(list(rows.values()))


def test_aim_over_a_random_event_falls_back_to_the_safe_point(tmp_path):
    styles = tmp_path / "styles.yaml"
    styles.write_text("styles:\n  - {name: centre, path: instant, aim: center}\n")
    game, fake = make_game(config(danger_color=(128, 0, 0)))
    game.mouse = MouseLab.load(MouseConfig(enabled=True, styles="styles.yaml"), tmp_path,
                               tmp_path)
    fake.img[100:160, 100:160] = TREE
    fake.img[125:135, 125:135] = (128, 0, 0)        # a random event in front of the middle
    blob = game.nearest(fake.grab(), TREE)
    assert game.click_blob(fake.grab(), blob)
    (pt, _), = fake.clicks
    zone = game.danger_zones(fake.grab())[0]
    assert not (zone.x <= pt[0] < zone.x + zone.w and zone.y <= pt[1] < zone.y + zone.h)
    assert game.mouse.pending is None and not game.mouse.bridge.pending
