import numpy as np
import pytest

from skillbot.game import BotError
from skillbot.menu import FILL, MenuBook, read_rows
from tests.fakes import config, make_game

HEADER, ROW = 19, 15
WORDS = {"Talk-to": [(0, 6), (2, 3), (0, 2), (5, 5)], "Trade": [(0, 5), (3, 3), (1, 4)],
         "Teleport": [(0, 8), (1, 1), (3, 6), (0, 3), (2, 2)]}


def draw_menu(img, point, options):
    x, y = point
    img[y:y + HEADER + ROW * len(options) + 2, x - 60:x + 60] = FILL
    img[y:y + HEADER, x - 60:x + 60] = 0
    for i, name in enumerate(options):
        mid = y + HEADER + ROW * i + ROW // 2
        cx = x - 55
        for j, (top, h) in enumerate(WORDS[name]):        # a made-up glyph per word
            img[mid - 4 + top % 4:mid - 4 + top % 4 + h, cx + 3 * j:cx + 3 * j + 2] = 255
        img[mid - 3:mid + 3, cx + 40:cx + 70] = (255, 255, 0)  # the thing's name, yellow


def test_rows_are_read_and_found_by_their_taught_word():
    img = np.zeros((503, 765, 3), np.uint8)
    draw_menu(img, (300, 100), ["Talk-to", "Trade", "Teleport"])
    rows = read_rows(img, (300, 100), HEADER, ROW)
    assert len(rows) == 3
    book = MenuBook()
    for name, sig in zip(["Talk-to", "Trade", "Teleport"], rows):
        book.learn(name, sig)
    other = np.zeros_like(img)
    draw_menu(other, (200, 150), ["Teleport", "Talk-to"])
    found = read_rows(other, (200, 150), HEADER, ROW)
    assert book.find("Teleport", found) == 1 and book.find("talk-to", found) == 2
    assert book.find("Trade", found) is None
    assert read_rows(np.zeros_like(img), (200, 150), HEADER, ROW) == []


def test_book_saves_and_loads(tmp_path):
    img = np.zeros((503, 765, 3), np.uint8)
    draw_menu(img, (300, 100), ["Trade"])
    book = MenuBook(tmp_path / "m.json")
    book.learn("Trade", read_rows(img, (300, 100), HEADER, ROW)[0])
    book.save()
    again = MenuBook(tmp_path / "m.json")
    assert again.knows("trade") and again.find("Trade", read_rows(img, (300, 100), HEADER, ROW)) == 1


def test_choose_picks_the_taught_row_and_refuses_a_missing_one(tmp_path):
    game, fake = make_game(config(data_dir=tmp_path))
    draw_menu(fake.img, (300, 100), ["Talk-to", "Trade", "Teleport"])
    rows = read_rows(fake.img, (300, 100), HEADER, ROW)
    for name, sig in zip(["Talk-to", "Trade", "Teleport"], rows):
        game.menus.learn(name, sig)
    game.choose((300, 100), "Teleport", 2)
    assert fake.clicks[-1][0] == (300, 100 + HEADER + 2 * ROW + ROW // 2)
    fake.img[:] = 0
    draw_menu(fake.img, (300, 100), ["Talk-to", "Trade"])
    with pytest.raises(BotError):
        game.choose((300, 100), "Teleport", 3)
    with pytest.raises(BotError):
        game.choose((300, 100), 3)


def test_an_untaught_word_uses_the_row_given(tmp_path):
    game, fake = make_game(config(data_dir=tmp_path))
    game.choose((300, 100), "Tan All", 5)        # no menu drawn: blind, as before
    assert fake.clicks[-1][0] == (300, 100 + HEADER + 4 * ROW + ROW // 2)
    with pytest.raises(BotError):
        game.choose((300, 100), "Tan All")
