import pytest
import yaml

from skillbot.colors import Registry, collisions, palette, resolve_config
from skillbot.config import Config
from skillbot.setup_check import check_setup, find_step, setup_text

from fakes import LAYOUT, blank, outline


def test_default_registry_has_no_clashes():
    reg = Registry.load()
    assert reg.entries and reg.check(25) == []


def test_example_config_loads_with_names():
    cfg = Config.load("config.example.yaml")
    assert cfg.bank_color == (255, 0, 255)
    assert cfg.items["bones"] == (255, 255, 255)
    assert cfg.plan[0].target == Registry.load().entries["tree"].rgb


def test_palette_avoids_greys_darks_and_health_bars():
    for c in palette(25):
        assert max(c) >= 192 and max(c) - min(c) >= 128
    assert (0, 255, 0) not in palette(25) and (255, 0, 0) not in palette(25)


def test_registry_rejects_unknown_names_and_categories(tmp_path):
    reg = Registry.load()
    with pytest.raises(ValueError, match="unknown color name"):
        reg.resolve("chartreuse")
    path = tmp_path / "c.yaml"
    path.write_text("x: {rgb: [1, 2, 3], category: sparkly}\n")
    with pytest.raises(ValueError, match="category"):
        Registry.load(path)


def test_items_and_world_colors_are_checked_separately(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({
        "tile": {"rgb": [255, 255, 255], "category": "route"},
        "bones": {"rgb": [255, 255, 255], "category": "item"},       # fine: different places
        "tile2": {"rgb": [250, 250, 250], "category": "route"},      # clash with tile
    }))
    assert Registry.load(path).check(25) == ["tile and tile2 are too similar"]


def test_scene_collision_is_reported(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "bank_color": [255, 0, 255],
        "items": {"logs": [0, 255, 0]},
        "routes": {"r": [[250, 10, 250]]},
        "plan": [{"name": "trees", "skill": "woodcutting", "task": "gather",
                  "target": [0, 255, 255], "items": ["logs"], "walk": {"bank": "r"}}]}))
    with pytest.raises(ValueError, match="bank / route r tile 1"):
        Config.load(cfg_file)


def test_same_route_tile_in_both_directions_is_fine():
    assert collisions({"a": (1, 2, 3), "b": (200, 2, 3)}, 25) == []
    raw = resolve_config({"routes": {"x": ["tile_white"]}, "items": ["logs"]}, Registry.load())
    assert raw["routes"]["x"] == [(255, 255, 255)] and raw["items"]["logs"] == (0, 255, 0)


def test_setup_text_lists_everything_for_a_step():
    cfg = Config.load("config.example.yaml")
    text = setup_text(cfg, find_step(cfg, "fire runes (Al Kharid)"), Registry.load())
    for expected in ("altar #00C080", "ruins #FF8000", "altar_portal #8000C0",
                     "fire_to_alkharid", "rune_essence: rune_essence", "bank #FF00FF"):
        assert expected in text
    with pytest.raises(SystemExit):
        find_step(cfg, "nope")
    assert find_step(cfg, "1").name == "normal trees"


def test_check_setup_from_screenshot():
    cfg = Config.load("config.example.yaml")
    step = find_step(cfg, "willows")
    reg = Registry.load()
    img = blank()
    assert {c.name: c.status for c in check_setup(cfg, step, img, reg)}["target"] == "FAIL"
    outline(img, 240, 150, 40, 30, reg.entries["willow_tree"].rgb)
    outline(img, 380, 60, 30, 30, cfg.bank_color)
    r = LAYOUT.slot(3)
    img[r.y + 6:r.y + r.h - 6, r.x + 6:r.x + r.w - 6] = (140, 110, 90)
    outline(img, r.x + 5, r.y + 5, r.w - 10, r.h - 10, cfg.items["willow_logs"])
    status = {c.name: c.status for c in check_setup(cfg, step, img, reg)}
    assert status["target"] == "PASS" and status["bank"] == "PASS"
    assert status["inventory tags"] == "PASS"
    assert status["route bank_to_willows tile 1"] == "WARN"      # not visible from here
