import json

from skillbot.colors import Entry, Registry
from skillbot.runelite_profile import (WikiIds, argb_hex, argb_int, build, read_properties,
                                       write_properties)

REG = Registry({
    "logs": Entry("logs", (0, 255, 0), "item"),
    "coin_pouch": Entry("coin_pouch", (10, 20, 30), "item"),
    "alch_item": Entry("alch_item", (1, 2, 3), "item"),
    "enemy": Entry("enemy", (192, 64, 255), "enemy"),
    "cow": Entry("cow", (255, 128, 255), "enemy"),
    "random_event": Entry("random_event", (128, 0, 0), "danger"),
    "fishing_spot": Entry("fishing_spot", (0, 255, 128), "resource"),
    "loot": Entry("loot", (255, 192, 0), "loot"),
    "bank": Entry("bank", (255, 0, 255), "bank"),
    "altar": Entry("altar", (5, 5, 5), "station"),
    "gilded_altar": Entry("gilded_altar", (6, 6, 6), "station"),
    "tile_plum": Entry("tile_plum", (128, 64, 192), "route"),
})
NAMES = {
    "npcs": {"cow": ["Cow"], "enemy": ["Hill Giant", "Mystery beast"],
             "random_event": ["Leo", "Nobody"], "fishing_spot": ["Fishing spot"]},
    "npc_ids": {"fishing_spot": [1518, 1530]},
    "objects": {"bank": ["Bank booth"], "altar": ["Altar"], "gilded_altar": ["Altar"]},
    "ground_items": ["Bones"],
}
PAGES = {"Cow": "{{Infobox Monster\n|id1 = 2790, 2791\n|id2 = 5842\n}}",
         "Hill Giant": "|id = 2098", "Leo": "|id1 = 6745\n|id2 = 6746",
         "Coin pouch": "|id1 = 22521\n|id2 = 22522"}


def fetch(url):
    if url.endswith("/mapping"):
        return [{"name": "Logs", "id": 1511}]
    from urllib.parse import unquote
    page = unquote(url.split("page=")[1])
    return {"parse": {"wikitext": {"*": PAGES.get(page, "no infobox here")}}}


def test_colors_in_runelite_formats():
    assert argb_int((255, 0, 0)) == "-65536" and argb_int((255, 128, 255)) == "-32513"
    assert argb_hex((0, 255, 128)) == "#FF00FF80"


def test_properties_round_trip():
    props = {"a.b": "x=y: z", "npcindicators.npcToHighlight": "Cow, Goblin",
             "weird key": " lead", "u": "café", "json": '{"color":"#FF00FF00"}'}
    text = write_properties(props)
    assert read_properties(text) == props
    assert read_properties("a = 1\nb:2\n# c=3\nlong=one \\\n    two\n") == {
        "a": "1", "b": "2", "long": "one two"}


def test_build_generates_tags_and_npc_colors(tmp_path):
    wiki = WikiIds(tmp_path / "ids.json", fetch=fetch)
    props, report = build(REG, NAMES, wiki)
    assert props["inventorytags.tag_1511"] == json.dumps({"color": "#FF00FF00"})
    assert {"inventorytags.tag_22521", "inventorytags.tag_22522"} <= set(props)
    assert any("alch_item" in r for r in report)
    assert props["npcindicators.highlightcolor_2790"] == argb_int((255, 128, 255))
    assert props["npcindicators.highlightcolor_5842"] == argb_int((255, 128, 255))
    assert props["npcindicators.highlightcolor_6745"] == argb_int((128, 0, 0))
    assert props["npcindicators.highlightcolor_1518"] == argb_int((0, 255, 128))
    names = props["npcindicators.npcToHighlight"].split(", ")
    # "Nobody" (a random event without ids) would show in the enemy color: left out
    assert names == ["Cow", "Hill Giant", "Mystery beast", "Leo", "Fishing spot"]
    assert any("Nobody" in r for r in report)
    assert props["npcindicators.npcColor"] == argb_int((192, 64, 255))
    assert props["grounditems.highlightedColor"] == argb_int((255, 192, 0))
    assert props["runelite.npcindicatorsplugin"] == "true"
    wiki.save()
    cached = WikiIds(tmp_path / "ids.json", fetch=lambda url: 1 / 0)   # no fetching now
    assert cached.npc("Cow") == [2790, 2791, 5842] and cached.items("Logs") == [1511]


def test_recolors_an_export_by_object_name_and_tile_label(tmp_path):
    base = {
        "npcindicators.npcToHighlight": "Banker",
        "objectindicators.region_12850": json.dumps([
            {"id": 10355, "name": "Bank booth", "regionId": 12850, "regionX": 1, "regionY": 2,
             "z": 0, "color": "#FFFF0000"},
            {"id": 409, "name": "Altar", "regionId": 12850, "regionX": 3, "regionY": 4, "z": 0,
             "color": -65536},
            {"id": 1, "name": "Chair", "regionId": 12850, "regionX": 5, "regionY": 6, "z": 0,
             "color": "#FFFF0000"}]),
        "groundMarker.region_12850": json.dumps([
            {"regionId": 12850, "regionX": 7, "regionY": 8, "z": 0, "color": "#FFFF0000",
             "label": "tile plum"},
            {"regionId": 12850, "regionX": 9, "regionY": 9, "z": 0, "color": "#FFFF0000"}]),
        "someplugin.setting": "kept",
    }
    props, report = build(REG, NAMES, WikiIds(tmp_path / "ids.json", fetch=fetch), base=base)
    objs = {o["name"]: o["color"] for o in json.loads(props["objectindicators.region_12850"])}
    assert objs == {"Bank booth": "#FFFF00FF", "Altar": -65536, "Chair": "#FFFF0000"}
    tiles = json.loads(props["groundMarker.region_12850"])
    assert tiles[0]["color"] == "#FF8040C0" and tiles[1]["color"] == "#FFFF0000"
    assert props["someplugin.setting"] == "kept"
    assert props["npcindicators.npcToHighlight"].startswith("Banker, Cow")
    text = "\n".join(report)
    assert "Object Markers: 1 recolored" in text and "Altar" in text and "Chair" in text
    assert "Ground Markers: 1 recolored" in text
