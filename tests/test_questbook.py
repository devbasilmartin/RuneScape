import numpy as np

from skillbot import questbook
from skillbot.layout import Layout
from skillbot.library import load_library
from skillbot.menu import MenuBook
from skillbot.places import load_places
from skillbot.colors import Registry

RED, YELLOW, GREEN = (255, 0, 0), (255, 255, 0), (13, 193, 13)


def tab(lines):
    """A fake quest tab: each line a pattern of 'text' pixels in its color."""
    lay = Layout()
    img = np.zeros((503, 765, 3), np.uint8)
    a = lay.quest_list
    for i, (pattern, color) in enumerate(lines):
        y = a.y + 6 + i * 15
        for j, on in enumerate(pattern):
            if on == "#":
                img[y:y + 9, a.x + 4 + j * 3:a.x + 6 + j * 3] = color
    return img, lay


def test_names_are_taught_once_and_read_in_any_color(tmp_path):
    img, lay = tab([("#.##.#", RED), ("##.###..#", YELLOW), ("#.#.#.#", GREEN)])
    book = MenuBook(tmp_path / "quest_words.json")
    y = lay.quest_list.y + 6 + 15 + 4
    assert questbook.teach(img, lay.quest_list, book, "Cook's Assistant", y) == "started"
    assert questbook.teach(img, lay.quest_list, book, "Imp Catcher",
                           lay.quest_list.y + 6 + 4) == "not started"
    later, _ = tab([("##.###..#", GREEN), ("#.#.#.#", GREEN), ("#.##.#", YELLOW)])
    states = questbook.tab_states(later, lay.quest_list, MenuBook(tmp_path / "quest_words.json"))
    assert states == {"cook's assistant": "finished", "imp catcher": "started"}


def test_quest_list_is_sound(tmp_path):
    from skillbot.goals import QuestLog
    quests = questbook.load_quests()
    places = load_places(Registry.load().resolve)
    for q in quests.values():
        assert q.start in places, q.name
    library_quests = {q for m in load_library().values() if not m.members
                      for q in m.requires_quests}
    assert library_quests <= set(quests)
    ready = QuestLog(tmp_path / "ready.json")
    knight = quests["The Knight's Sword"]
    assert any("mining 10" in p for p in questbook.problems(knight, {"mining": 5}, "f2p", ready))
    assert any("quest-ready" in p for p in questbook.problems(knight, {"mining": 10}, "f2p",
                                                               ready))
    ready.add("The Knight's Sword")
    assert questbook.problems(knight, {"mining": 10}, "f2p", ready) == []
    assert questbook.problems(quests["Rune Mysteries"], {}, "f2p", ready) == []
