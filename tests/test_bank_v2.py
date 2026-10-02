import pytest

from skillbot.config import Step, Withdraw
from skillbot.planner import make_task

import fakes
from fakes import BANK, LAYOUT, config, make_game, outline, slot_at


def put_item(img, slot, name):
    old = dict(fakes.ITEMS)
    fakes.ITEMS.update(EXTRA)
    try:
        fakes.put_item(img, slot, name)
    finally:
        fakes.ITEMS.clear()
        fakes.ITEMS.update(old)

EXTRA = {"knife": (0, 192, 255), "longbow_u": (192, 255, 64)}


class TabBank:
    """A bank showing one Bank Tags tab after `tag:<name>` is searched; each tab slot
    holds (item, stock). Withdrawals follow the selected quantity button."""

    def __init__(self, fake, tabs):
        self.fake, self.tabs = fake, tabs
        self.open, self.tab, self.quantity, self.typed = False, None, "1", []
        outline(fake.img, 380, 60, 30, 30, BANK)
        fake.on_click.append(self.click)
        fake.on_key.append(lambda f, k: self.close() if k == "esc" else None)
        orig_type = fake.type_text

        def type_text(text):
            orig_type(text)
            self.typed.append(text)
            if self.open and text.startswith("tag:"):
                self.tab = text[4:]
        fake.type_text = type_text

    def close(self):
        self.open, self.tab = False, None

    def click(self, fake, pt):
        if 380 <= pt[0] < 410 and 60 <= pt[1] < 90:
            self.open = True
            return
        if not self.open:
            return
        for q, qpt in LAYOUT.bank_quantity.items():
            if tuple(pt) == qpt:
                self.quantity = q
                return
        i = slot_at(pt)
        if i is not None:                       # deposit that item's stack
            name = fake.items().get(i)
            for j, n in fake.items().items():
                if n == name:
                    put_item(fake.img, j, None)
            return
        for b in range(32):
            r = LAYOUT.bank_slot(b)
            if r.x <= pt[0] < r.x + r.w and r.y <= pt[1] < r.y + r.h and self.tab:
                slots = self.tabs.get(self.tab, [])
                if b >= len(slots):
                    return
                name, stock = slots[b]
                free = [k for k in range(1, 28) if k not in fake.items()]
                n = {"1": 1, "5": 5, "10": 10, "x": 14, "all": len(free)}[self.quantity]
                n = min(n, stock, len(free))
                for k in free[:n]:
                    put_item(fake.img, k, name)
                slots[b] = (name, stock - n)


def test_withdraw_parsing():
    assert Withdraw.parse(3) == Withdraw(3)
    assert Withdraw.parse({"slot": 1, "item": "logs", "quantity": "ALL"}) == \
        Withdraw(1, "logs", "all")
    with pytest.raises(ValueError):
        Withdraw.parse({"slot": 1, "quantity": "7"})


def test_with_item_needs_process_and_use_item():
    with pytest.raises(ValueError, match="with_item"):
        Step.from_dict(dict(name="x", skill="fletching", task="gather", items=["logs"],
                            with_item="logs", target=(1, 2, 3)))
    step = Step.from_dict(dict(name="x", skill="fletching", task="process", items=["logs"],
                               use_item="knife", with_item="logs"))
    assert step.target is None


def fletch_step(**kw):
    return dict(name="fletch", skill="fletching", task="process", items=["logs"],
                use_item="knife", with_item="logs", bank_tab="fletching", tools=0,
                withdraw=[{"slot": 0, "item": "logs", "quantity": "all"}], idle_timeout=5,
                **kw)


def knife_world(fake):
    """Knife untagged... no: tagged so the bot can find it; it lives in slot 0."""
    put_item(fake.img, 0, "knife")
    state = {"selected": None, "menu": False, "making": False}

    def click(f, pt):
        i = slot_at(pt)
        if i is None:
            return
        name = f.items().get(i)
        if state["selected"] == "knife" and name == "logs":
            state["menu"] = True
            state["selected"] = None
        else:
            state["selected"] = name

    def key(f, k):
        if k == "space" and state["menu"]:
            state["menu"], state["making"] = False, True

    def tick(f):
        if state["making"]:
            logs = sorted(i for i, n in f.items().items() if n == "logs")
            if not logs:
                state["making"] = False
                return
            put_item(f.img, logs[0], "longbow_u")
    fake.on_click.append(click)
    fake.on_key.append(key)
    fake.on_wait.append(tick)
    return state


def test_item_on_item_with_bank_tab_and_stock_check():
    cfg = config(extra_items=EXTRA)
    game, fake = make_game(cfg)
    fake.items = lambda: game.inv.tags(fake.img)
    bank = TabBank(fake, {"fletching": [("logs", 40)]})
    knife_world(fake)
    sent = []
    import skillbot.notify as n
    orig, n.notify = n.notify, sent.append
    try:
        task = make_task(game, Step.from_dict(fletch_step(keep=["knife"])))
        assert task.run_batch() == "ok"                  # 27 logs withdrawn and fletched
        assert "tag:fletching" in bank.typed
        assert list(fake.items().values()).count("longbow_u") == 27
        assert task.run_batch() == "ok"                  # the last 13 logs
        assert task.run_batch() == "exhausted"           # only a placeholder left
        assert task.run_batch() == "exhausted"
        assert len([m for m in sent if "out of logs" in m]) == 1   # told once
    finally:
        n.notify = orig
