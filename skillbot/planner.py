"""Works through the plan: picks the step to train, reads levels, recovers from errors."""
import json
import logging
from pathlib import Path

from .config import Step
from .game import BotError, Game, StopBot
from .combat import CombatTask
from .runecraft import RunecraftTask
from .skills import SkillReader
from .status import write_status
from .tasks import FiremakingTask, GatherTask, ProcessTask

TASK_TYPES = {"gather": GatherTask, "process": ProcessTask, "firemaking": FiremakingTask,
              "combat": CombatTask, "runecraft": RunecraftTask}


def make_task(game: Game, step: Step):
    return TASK_TYPES[step.task](game, step)

log = logging.getLogger("skillbot")


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
                self.levels[skill] = level
        self.save()

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps({"levels": self.levels}, indent=1))


class Planner:
    def __init__(self, game: Game, levels: Levels, session=None, status_dir=None):
        self.game = game
        self.status_dir = status_dir
        self.levels = levels
        self.session = session
        self.errors = 0

    def done(self, step: Step) -> bool:
        return self.levels.get(step.skill) >= step.until_level

    def run(self) -> None:
        g = self.game
        plan = g.cfg.plan
        if not plan:
            raise StopBot("the plan in config.yaml is empty")
        deadline = g.now() + g.cfg.max_runtime_hours * 3600 if g.cfg.max_runtime_hours else None
        self._guard(g.setup_camera)
        self._guard(lambda: self.levels.refresh({s.skill for s in plan}))
        while True:
            progressed = False
            for step in plan:
                if self.done(step):
                    continue
                progressed |= self.run_step(step, deadline) > 0
                if deadline and g.now() >= deadline:
                    raise StopBot("max_runtime_hours reached")
            if all(self.done(s) for s in plan):
                raise StopBot("plan complete")
            if not progressed:
                raise StopBot("no step could make progress (out of supplies everywhere?)")

    def report(self, step: Step, task, started: float) -> None:
        if self.status_dir is None:
            return
        write_status(self.status_dir, step=step.name, skill=step.skill,
                     level=self.levels.get(step.skill), target=step.until_level,
                     since=started, stats=dict(task.stats))

    def run_step(self, step: Step, deadline=None) -> int:
        g = self.game
        log.info("step %r: %s %d -> %d", step.name, step.skill,
                 self.levels.get(step.skill), step.until_level)
        task = make_task(g, step)
        # Until every digit is known, read after each item so levels change one at a time.
        task.on_progress = lambda: (None if self.levels.reader.complete()
                                    else self.levels.refresh([step.skill]))
        started, batches = g.now(), 0
        self.report(step, task, started)
        while not self.done(step):
            if step.max_minutes and g.now() - started >= step.max_minutes * 60:
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
        log.info("step %r: %d batches, %s", step.name, batches, task.stats)
        return batches

    def _guard(self, action):
        """Run ``action``; on a BotError, recover and return None instead of raising."""
        if self.session:
            self.session.ensure()
        try:
            self.game.keep_running()
            result = action()
        except BotError as e:
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
