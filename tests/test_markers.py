from pathlib import Path

from skillbot.colors import Registry
from skillbot.library import load_library
from skillbot.markers import marker_list

DOC = Path(__file__).resolve().parent.parent / "docs" / "markers.md"


def test_marker_list_is_current():
    assert DOC.read_text() == marker_list(load_library(), Registry.load()), \
        "docs/markers.md is out of date: run python -m skillbot marker-list"


def test_marker_list_kinds():
    text = marker_list(load_library(), Registry.load())
    assert "Object Marker on Hopper → `hopper`" in text            # recolored by name
    assert "Ground Marker labelled `afk_spot`" in text               # by label
    assert "shares the name Portal" in text                          # by hand
    assert "obstacle 1 of the course" in text
    assert "Inventory Tag by hand on the item you use: `tithe_seed`" in text
    yews = text.split("## woodcutting guild yews")[1].split("##")[0]
    assert "`yew_logs`" in yews and "Yew tree" in yews
