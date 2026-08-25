"""Best-effort, in-memory request deduplication and rate limiting."""

import threading
import time
from typing import Literal


class MemoryRequestGuard:
    """Guard requests using per-event expiry and per-room rate windows."""

    def __init__(self) -> None:
        self._events: dict[str, tuple[str, float, float]] = {}
        self._accepted_at_by_room: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def claim(
        self,
        event_key: str,
        room_key: str,
        *,
        limit: int,
        rate_window_seconds: int,
        dedupe_window_seconds: int,
        now: float | None = None,
    ) -> Literal["accepted", "duplicate", "rate_limited"]:
        """Claim an event, returning its deduplication or rate-limit outcome."""
        self._validate_bounds(limit, rate_window_seconds, dedupe_window_seconds)
        current_time = time.monotonic() if now is None else now

        with self._lock:
            self._prune_expired(current_time)

            if event_key in self._events:
                return "duplicate"

            rate_window_start = current_time - rate_window_seconds
            current_room_count = sum(
                1
                for created_at in self._accepted_at_by_room.get(room_key, [])
                if rate_window_start < created_at <= current_time
            )
            if current_room_count >= limit:
                return "rate_limited"

            self._events[event_key] = (
                room_key,
                current_time,
                current_time + dedupe_window_seconds,
            )
            self._accepted_at_by_room.setdefault(room_key, []).append(current_time)
            return "accepted"

    @staticmethod
    def _validate_bounds(
        limit: int,
        rate_window_seconds: int,
        dedupe_window_seconds: int,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if rate_window_seconds <= 0:
            raise ValueError("rate_window_seconds must be positive")
        if dedupe_window_seconds <= 0:
            raise ValueError("dedupe_window_seconds must be positive")

    def _prune_expired(self, now: float) -> None:
        expired_event_keys = [
            event_key
            for event_key, (_, _, expires_at) in self._events.items()
            if expires_at <= now
        ]
        for event_key in expired_event_keys:
            del self._events[event_key]
