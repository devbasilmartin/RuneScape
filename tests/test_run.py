from skillbot.config import Step
from skillbot.planner import make_task
from skillbot.run import RunManager

from fakes import LAYOUT, TREE, config, make_game, outline

ON, OFF = (230, 200, 40), (90, 90, 90)


class Orb:
    """The run orb. Clicking toggles run if there is energy; running drains energy."""

    def __init__(self, fake, running=False, energy=100.0, drain=0.0, regen=0.0):
        self.fake, self.running, self.energy = fake, running, energy
        self.drain, self.regen, self.clicks, self.last = drain, regen, 0, fake.t
        fake.on_click.append(self.click)
        fake.on_wait.append(self.tick)
        self.draw()

    def draw(self):
        x, y = LAYOUT.run_orb
        self.fake.img[y - 4:y + 5, x - 4:x + 5] = ON if self.running else OFF

    def click(self, fake, pt):
        if tuple(pt) == LAYOUT.run_orb:
            self.clicks += 1
            if self.running:
                self.running = False
            elif self.energy >= 1:
                self.running = True
            self.draw()

    def tick(self, fake):
        dt, self.last = fake.t - self.last, fake.t
        if self.running:
            self.energy -= self.drain * dt
            if self.energy <= 0:
                self.energy, self.running = 0, False
        else:
            self.energy = min(100, self.energy + self.regen * dt)
        self.draw()


def manager(game, retry=60):
    game.run = RunManager(game, ON, OFF, retry=retry)
    return game.run


def test_turns_run_on_and_leaves_it_on():
    game, fake = make_game(config())
    orb = Orb(fake)
    run = manager(game)
    for _ in range(5):
        run.maintain()
        fake.wait(6)
    assert orb.running and orb.clicks == 1


def test_waits_after_running_out_then_turns_back_on():
    game, fake = make_game(config())
    orb = Orb(fake, running=True, energy=10, drain=1.0, regen=0.5)
    run = manager(game, retry=60)
    clicks_at = []
    for _ in range(40):
        before = orb.clicks
        run.maintain()
        if orb.clicks > before:
            clicks_at.append(fake.t)
        fake.wait(5)
    assert run.stats["ran_out"] >= 1
    assert clicks_at and clicks_at[0] >= 60          # not straight after running out
    assert orb.clicks <= 3


def test_no_click_spam_with_zero_energy():
    game, fake = make_game(config())
    orb = Orb(fake, energy=0)
    run = manager(game, retry=60)
    for _ in range(30):
        run.maintain()
        fake.wait(5)
    assert orb.clicks <= 3       # one try per minute over ~150s


def test_unknown_orb_does_nothing():
    game, fake = make_game(config())
    run = manager(game)
    run.maintain()                # orb area is plain background: logged out / hidden
    assert fake.clicks == []


def test_run_is_managed_while_gathering():
    game, fake = make_game(config())
    orb = Orb(fake)
    manager(game)
    outline(fake.img, 240, 150, 40, 30, TREE)
    task = make_task(game, Step.from_dict(dict(
        name="t", skill="woodcutting", task="gather", target=TREE, items=["logs"],
        idle_timeout=4)))
    try:
        task.run_batch()
    except Exception:
        pass                      # no logs ever arrive; we only care that run got switched on
    assert orb.running
