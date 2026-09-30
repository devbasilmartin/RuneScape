import pytest

from skillbot import vision
from skillbot.config import Config
from skillbot.inventory import Inventory

from fakes import ITEMS, LAYOUT, blank, outline, put_item


def test_find_blobs_joins_outline_and_reports_box():
    img = blank()
    outline(img, 100, 120, 40, 30, (0, 255, 255))
    outline(img, 300, 50, 20, 20, (0, 250, 250))
    blobs = vision.find_blobs(img, (0, 255, 255), 25, region=LAYOUT.viewport)
    assert len(blobs) == 2
    assert (blobs[0].x, blobs[0].y, blobs[0].w) == (97, 117, 46)
    assert vision.nearest(blobs, (310, 60)).center == blobs[1].center


def test_color_tolerance_rejects_other_colors():
    img = blank()
    outline(img, 100, 120, 40, 30, (255, 0, 255))
    assert vision.find_blobs(img, (0, 255, 255), 25) == []


def test_inventory_reads_tags_and_ignores_untagged():
    inv = Inventory(LAYOUT, ITEMS, tools=1)
    img = blank()
    put_item(img, 5, "raw_shrimps")
    put_item(img, 6, "logs")
    assert inv.tags(img) == {5: "raw_shrimps", 6: "logs"}
    assert inv.slots_with(img, "logs") == [6]
    assert not inv.is_full(img)
    for i in range(1, 28):
        put_item(img, i, "burnt_fish")
    assert inv.is_full(img)
    assert not inv.is_full(img, tools=0)


def test_config_rejects_similar_item_colors():
    cfg = Config(items={"a": (0, 255, 0), "b": (0, 225, 20)})
    with pytest.raises(ValueError, match="too similar"):
        cfg.validate()
