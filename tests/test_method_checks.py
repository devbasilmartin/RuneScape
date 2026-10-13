import numpy as np

from skillbot.colors import Registry
from skillbot.config import Config
from skillbot.doctor import FAIL, PASS, WARN
from skillbot.library import load_library
from skillbot.menu import MenuBook
from skillbot.places import load_places
from skillbot.setup_check import method_checks


def run(method_id, clicks=None, account="members", scale=None):
    reg = Registry.load(Config().colors_file)
    method = load_library()[method_id]
    cfg = Config(account=account)
    img = np.zeros((503, 765, 3), np.uint8)
    return {c.name: c for c in method_checks(cfg, method, img, reg, clicks or {}, MenuBook(),
                                             load_places(reg.resolve), scale)}


def test_tanning_needs_its_click_and_menus_and_the_map():
    checks = run("tan_cowhides")
    assert checks["taught tan_soft_leather"].status == FAIL
    assert checks["menu 'Tan All'"].status == WARN and "row 5" in checks["menu 'Tan All'"].detail
    assert checks["world map"].status == WARN
    assert checks["marker tanner"].status == WARN
    checks = run("tan_cowhides", clicks={"tan_soft_leather": (1, 2)}, scale=3.0)
    assert checks["taught tan_soft_leather"].status == PASS and "world map" not in checks


def test_members_methods_fail_on_an_f2p_account():
    members = next(m for m, v in load_library().items() if v.members)
    assert run(members, account="f2p")["account"].status == FAIL
