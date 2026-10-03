"""Works through the plan: picks the step to train, reads levels, recovers from errors."""
import json
import logging
from pathlib import Path

from .config import Step
from .game import BotError, Game, StopBot
from .combat import CombatTask, StandingCombatTask
from .construction import ConstructionTask
from .quest import QuestTask
from .routine import RoutineTask
from .slayer import SlayerTask
from .thieving import ThieveTask
from .agility import AgilityTask
from .magic import CastTask
from .runecraft import RunecraftTask
from .skills import SkillReader
from .history import log_event
from .notify import notify
from .status import write_status
from .trust import TRIAL_SLICE_MINUTES, fingerprint
from .tasks import FiremakingTask, GatherTask, ProcessTask

TASK_TYPES = {"gather": GatherTask, "process": ProcessTask, "firemaking": FiremakingTask,
              "combat": CombatTask, "runecraft": RunecraftTask, "cast": CastTask,
              "agility": AgilityTask, "construction": ConstructionTask, "thieve": ThieveTask,
              "routine": RoutineTask, "quest": QuestTask,
              "slayer": SlayerTask}


def make_task(game: Game, step: Step):
    if step.task == "combat" and step.stand_on is not None:
        return StandingCombatTask(game, step)
    return TASK_TYPES[step.task](game, step)


log = logging.getLogger("skillbot")
HANDOVER = "handover"            # StopBot reason: the rotation's turn is over


class Levels:
    """Known levels, refreshed from the skills tab and saved to data/progress.json."""

    def __init__(self, game: Game, reader: SkillReader, path: Path | None = None,
                 levels: dict | None = None):
        self.game = game
        self.reader = reader
        self.path = path
        self.levels = dict(levels or {})

    @classmethod
    def load(cls, game: Game, reader: SkillReader, data_dir: Path) -> "Levels":
        path = data_dir / "progress.json"
        levels = json.loads(path.read_text()).get("levels", {}) if path.exists() else {}
        return cls(game, reader, path, levels)

    def get(self, skill: str) -> int:
        return self.levels.get(skill, 1)

    on_level_up = None          # fn(skill, old, new): upgrade notices

    def refresh(self, skills) -> None:
        g = self.game
        g.open_tab("skills")
        img = g.grab()
        g.open_tab("inventory")
        for skill in skills:
            level = self.reader.read_expecting(img, skill, self.get(skill))
            if level is None:
                log.warning("could not read the %s level (known digits: %s); keeping %d",
                            skill, self.reader.known_digits() or "none", self.get(skill))
            elif level < self.get(skill):
                log.warning("%s read as %d but was %d; ignoring", skill, level, self.get(skill))
            else:
                if level > self.get(skill):
                    log.info("%s level %d", skill, level)
                    if self.on_level_up:
                        self.on_level_up(skill, self.get(skill), level)
                self.levels[skill] = level
        self.save()

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps({"levels": self.levels}, indent=1))


class Planner:
    def __init__(self, game: Game, levels: Levels, session=None, status_dir=None,
                 trust=None, supervised: bool = False, notify=notify):
        self.game = game
        self.status_dir = status_dir
        self.trust = trust              # TrustStore, or None to run every step as trusted
        self.supervised = supervised
        self.notify = notify
        self.safety = None              # Safety: random events, deaths, world hopping
        self.chooser = None             # goals.Chooser: pick steps from goals + the library
        self.last_method = {}           # skill -> method id last used (to announce switches)
        self.current = None             # the step being run, for error accounting
        self.tainted = False            # a supervised run of the current step hit an error
        self.skipped = set()
        self.levels = levels
        self.session = session
        self.errors = 0

    def done(self, step: Step) -> bool:
        return self.levels.get(step.skill) >= step.until_level

    def run(self) -> None:
        g = self.game
        plan = g.cfg.plan
        deadline = g.now() + g.cfg.max_runtime_hours * 3600 if g.cfg.max_runtime_hours else None
        if not plan and self.chooser is None:
            raise StopBot("the plan in config.yaml is empty (and there's no goals.yaml)")
        if self.chooser is not None:
            return self.run_goals(deadline)
        self._guard(lambda: self.resync({s.skill for s in plan}))
        while True:
            progressed = False
            for step in plan:
                if self.done(step) or not self.allowed(step):
                    continue
                progressed |= self.run_step(step, deadline) > 0
                if deadline and g.now() >= deadline:
                    raise StopBot("max_runtime_hours reached")
            if all(self.done(s) for s in plan):
                raise StopBot("plan complete")
            if not progressed:
                if self.skipped and all(self.done(s) or s.name in self.skipped for s in plan):
                    raise StopBot("only experimental steps are left: run them with "
                                  "`run --supervised` while you watch")
                raise StopBot("no step could make progress (out of supplies everywhere?)")

    def run_goals(self, deadline=None) -> None:
        """Goals mode: ask the chooser what to train, run it, repeat."""
        from .skills import SKILLS
        g = self.game
        self._guard(lambda: self.resync(SKILLS))
        while True:
            if deadline and g.now() >= deadline:
                raise StopBot("max_runtime_hours reached")
            decision = self.chooser.next(self.levels.levels, g.now())
            if decision is None:
                raise StopBot("nothing left to train with the methods available "
                              "(see `python -m skillbot plan --explain`)")
            log.info("goals: %s %d -> %d with %r (%s)", decision.skill,
                     self.levels.get(decision.skill), decision.target, decision.method.name,
                     decision.phase)
            last = self.last_method.get(decision.skill)
            if last and last != decision.method.id:
                self.notify(f"{decision.skill.title()}: switching from {last} to "
                            f"{decision.method.id} ({self.chooser.profit(decision.method):+,.0f} gp/h)")
            self.last_method[decision.skill] = decision.method.id
            if self.run_step(decision.step, deadline) == 0:
                self.chooser.rest(decision.method.id, g.now() + 1800)   # out of supplies

    def allowed(self, step: Step) -> bool:
        """Experimental steps only run supervised (you're watching)."""
        if self.trust is None or self.supervised:
            return True
        code = fingerprint(step, TASK_TYPES[step.task])
        _, message = self.trust.record(step.name, code)
        if message:
            self.notify(message)
        if self.trust.level(step.name) == "experimental":
            if step.name not in self.skipped:
                self.skipped.add(step.name)
                self.notify(f"skipping {step.name!r}: it's experimental; run it with "
                            "`run --supervised` while you watch")
            return False
        return True

    def report(self, step: Step, task, started: float) -> None:
        if self.status_dir is None:
            return
        write_status(self.status_dir, step=step.name, skill=step.skill,
                     level=self.levels.get(step.skill), target=step.until_level,
                     since=started, stats=dict(task.stats))

    def resync(self, skills) -> None:
        """Get back to a known state when starting, including after you played
        (`resume`): close whatever is open, inventory tab, camera, fresh levels.
        Where the character stands is handled by each task (and, once navigation
        exists, by teleporting to a hub when the location is unknown)."""
        g = self.game
        g.close_interfaces()
        g.close_interfaces()
        g.open_tab("inventory")
        g.setup_camera()
        self.levels.refresh(skills)

    def run_step(self, step: Step, deadline=None) -> int:
        g = self.game
        log.info("step %r: %s %d -> %d", step.name, step.skill,
                 self.levels.get(step.skill), step.until_level)
        task = make_task(g, step)
        self.current, self.tainted = step, False
        level = "trusted"
        if self.trust is not None:
            self.trust.record(step.name, fingerprint(step, TASK_TYPES[step.task]))
            level = self.trust.level(step.name)
        slice_minutes = step.max_minutes
        if level == "trial" and not self.supervised:
            slice_minutes = min(step.max_minutes or TRIAL_SLICE_MINUTES, TRIAL_SLICE_MINUTES)
        # Until every digit is known, read after each item so levels change one at a time.
        task.on_progress = lambda: (None if self.levels.reader.complete()
                                    else self.levels.refresh([step.skill]))
        started, batches = g.now(), 0
        first_level = self.levels.get(step.skill)
        self.report(step, task, started)
        if step.location and getattr(g, "nav", None) is not None:
            arrive = step.target if step.target is not None else g.cfg.bank_color
            self._guard(lambda: g.nav.travel(step.location, arrive))
        try:
            batches = self._run_batches(step, task, started, slice_minutes, deadline)
        except StopBot as e:
            if self.trust is not None and not self.supervised and str(e) != HANDOVER:
                self.trust.add_stop(step.name)
            raise
        finally:
            self.current = None
            if self.status_dir is not None:
                log_event(self.status_dir, "step", step=step.name, skill=step.skill,
                          **{"from": first_level}, to=self.levels.get(step.skill),
                          target=step.until_level, minutes=round((g.now() - started) / 60, 1),
                          stats=dict(task.stats))
            if self.trust is not None and not self.tainted:
                self.trust.add_time(step.name, g.now() - started, self.supervised)
                message = self.trust.evaluate(step.name)
                if message:
                    self.notify(message)
        if level == "trial" and not self.supervised:
            self.notify(f"trial report: {step.name!r} ran {(g.now() - started) / 60:.0f} min, "
                        f"{batches} batches, {task.stats}; {self.trust.progress(step.name)}")
        log.info("step %r: %d batches, %s", step.name, batches, task.stats)
        return batches

    def handover_requested(self) -> bool:
        """The supervisor wants the next account: stop between batches."""
        return self.status_dir is not None and (Path(self.status_dir) / "handover").exists()

    def _run_batches(self, step: Step, task, started: float, slice_minutes, deadline) -> int:
        g, batches = self.game, 0
        while not self.done(step):
            if self.handover_requested():
                raise StopBot(HANDOVER)
            if self.safety is not None:
                self._guard(lambda: self.safety.between_batches(step))
            if slice_minutes and g.now() - started >= slice_minutes * 60:
                log.info("step %r: time slice over", step.name)
                break
            if deadline and g.now() >= deadline:
                break
            result = self._guard(task.run_batch)
            if result == "exhausted":
                break
            if result == "ok":
                batches += 1
                self._guard(lambda: self.levels.refresh([step.skill]))
                self.report(step, task, started)
        return batches

    def _guard(self, action):
        """Run ``action``; on a BotError, recover and return None instead of raising."""
        if self.session:
            self.session.ensure()
        try:
            self.game.keep_running()
            if self.safety is not None:
                self.safety.check(self.current)
            result = action()
        except BotError as e:
            step = self.current
            if self.trust is not None and step is not None:
                self.trust.add_error(step.name, self.supervised)
            if self.supervised:
                self.tainted = True
                raise StopBot(f"supervised run: stopping at the first error ({e}) so you "
                              "can see what happened") from e
            self.errors += 1
            log.warning("error %d/%d: %s", self.errors, self.game.cfg.max_consecutive_errors, e)
            if self.errors >= self.game.cfg.max_consecutive_errors:
                raise StopBot(f"{self.errors} errors in a row, last: {e}") from e
            self.recover()
            return None
        self.errors = 0
        return result

    def recover(self) -> None:
        g = self.game
        g.controls.key_up("shift")
        g.close_interfaces()
        g.close_interfaces()
        if self.session:
            self.session.ensure()
        g.open_tab("inventory")
        g.wait(2, 4)
