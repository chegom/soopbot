"""Best-effort, in-memory conversation history for a warm serverless instance."""

from dataclasses import dataclass
import threading
import time


HISTORY_TTL_SECONDS = 1800


@dataclass(frozen=True)
class Turn:
    """One answered question and the reply the room actually saw."""

    question: str
    answer: str


class MemoryConversationLog:
    """Keep recent turns so a follow-up question can reach the model with context.

    The log lives only in the current warm instance: a new instance starts empty
    and instances never share turns. Callers must treat it as best effort.
    """

    MAX_TURNS = 20

    def __init__(self) -> None:
        self._turns: list[tuple[Turn, float]] = []
        self._lock = threading.Lock()

    def record(self, question: str, answer: str, *, now: float | None = None) -> None:
        current_time = time.monotonic() if now is None else now
        with self._lock:
            self._prune_expired(current_time)
            self._turns.append((Turn(question, answer), current_time))
            overflow = len(self._turns) - self.MAX_TURNS
            if overflow > 0:
                del self._turns[:overflow]

    def recent(self, *, limit: int, now: float | None = None) -> tuple[Turn, ...]:
        if limit < 1:
            return ()
        current_time = time.monotonic() if now is None else now
        with self._lock:
            self._prune_expired(current_time)
            return tuple(turn for turn, _ in self._turns[-limit:])

    def size(self) -> int:
        with self._lock:
            return len(self._turns)

    def _prune_expired(self, current_time: float) -> None:
        cutoff = current_time - HISTORY_TTL_SECONDS
        self._turns = [item for item in self._turns if item[1] > cutoff]
