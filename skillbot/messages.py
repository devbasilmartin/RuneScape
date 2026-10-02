"""File-based mailbox between the bot/supervisor and the Discord service.

Everything lives under data/discord/ as small JSON files, so neither side needs the
other to be running: messages wait in the outbox until the Discord service delivers
them, and questions stay open until you answer, even across restarts.

    outbox/<id>.json    messages to send (notifications, questions, summaries)
    asks/<id>.json      open questions (removed when answered)
    answers/<id>.json   your answers, picked up by whoever asked
"""
import json
import time
import uuid
from pathlib import Path


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)                # atomic: readers never see half a file


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


class Mailbox:
    def __init__(self, data_dir: Path, clock=time.time):
        self.root = Path(data_dir) / "discord"
        self.clock = clock

    def _dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---- bot side ----------------------------------------------------------------------
    def post(self, text: str, kind: str = "notify", image: str | None = None) -> str:
        msg_id = f"{int(self.clock() * 1000):013d}-{uuid.uuid4().hex[:6]}"
        _write(self._dir("outbox") / f"{msg_id}.json",
               {"id": msg_id, "kind": kind, "text": text, "image": image,
                "created": self.clock()})
        return msg_id

    def ask(self, question: str, options: list[str], key: str | None = None) -> str:
        """Ask a question. Returns its id; poll ``answer(id)`` for the reply.

        ``key`` makes the question idempotent: asking the same key again while it's
        still open returns the existing id instead of asking twice (e.g. after a restart).
        """
        if key:
            for path in self._dir("asks").glob("*.json"):
                data = _read(path)
                if data and data.get("key") == key:
                    return data["id"]
        ask_id = self.post(question, kind="ask")
        _write(self._dir("asks") / f"{ask_id}.json",
               {"id": ask_id, "key": key, "question": question, "options": list(options),
                "created": self.clock()})
        outbox = self._dir("outbox") / f"{ask_id}.json"
        data = _read(outbox)
        data["options"] = list(options)
        _write(outbox, data)
        return ask_id

    def answer(self, ask_id: str) -> str | None:
        """The answer to a question, once (it's consumed when read)."""
        path = self._dir("answers") / f"{ask_id}.json"
        data = _read(path)
        if data is None:
            return None
        path.unlink(missing_ok=True)
        return data["answer"]

    # ---- Discord side ------------------------------------------------------------------
    def pending(self) -> list[dict]:
        out = []
        for path in sorted(self._dir("outbox").glob("*.json")):
            data = _read(path)
            if data:
                out.append(data)
        return out

    def delivered(self, msg_id: str) -> None:
        (self._dir("outbox") / f"{msg_id}.json").unlink(missing_ok=True)

    def open_asks(self) -> list[dict]:
        asks = [_read(p) for p in sorted(self._dir("asks").glob("*.json"))]
        return [a for a in asks if a]

    def reply(self, ask_id: str, answer: str) -> bool:
        """Record your answer. False if the question is no longer open."""
        ask_path = self._dir("asks") / f"{ask_id}.json"
        if not ask_path.exists():
            return False
        _write(self._dir("answers") / f"{ask_id}.json", {"answer": answer, "time": self.clock()})
        ask_path.unlink(missing_ok=True)
        return True
