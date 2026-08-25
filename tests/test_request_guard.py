import unittest

from soopbot.request_guard import MemoryRequestGuard


class MemoryRequestGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = MemoryRequestGuard()

    def test_first_request_is_accepted(self) -> None:
        outcome = self.guard.claim(
            "event-1",
            "room-1",
            limit=2,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=100.0,
        )

        self.assertEqual("accepted", outcome)

    def test_duplicate_event_is_rejected_within_its_dedupe_window(self) -> None:
        self.guard.claim(
            "event-1",
            "room-1",
            limit=2,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=100.0,
        )

        outcome = self.guard.claim(
            "event-1",
            "room-1",
            limit=2,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=101.0,
        )

        self.assertEqual("duplicate", outcome)

    def test_distinct_request_over_room_limit_is_rate_limited(self) -> None:
        self.guard.claim(
            "event-1",
            "room-1",
            limit=1,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=100.0,
        )

        outcome = self.guard.claim(
            "event-2",
            "room-1",
            limit=1,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=101.0,
        )

        self.assertEqual("rate_limited", outcome)

    def test_request_is_accepted_after_its_rate_window(self) -> None:
        self.guard.claim(
            "event-1",
            "room-1",
            limit=1,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=100.0,
        )

        outcome = self.guard.claim(
            "event-2",
            "room-1",
            limit=1,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=160.0,
        )

        self.assertEqual("accepted", outcome)

    def test_short_dedupe_window_does_not_bypass_longer_rate_window(self) -> None:
        self.guard.claim(
            "event-1",
            "room-1",
            limit=1,
            rate_window_seconds=60,
            dedupe_window_seconds=1,
            now=100.0,
        )

        outcome = self.guard.claim(
            "event-2",
            "room-1",
            limit=1,
            rate_window_seconds=60,
            dedupe_window_seconds=1,
            now=102.0,
        )

        self.assertEqual("rate_limited", outcome)

    def test_obsolete_rate_history_is_pruned_and_empty_rooms_are_removed(self) -> None:
        self.guard.claim(
            "event-old-1",
            "room-old",
            limit=10,
            rate_window_seconds=3600,
            dedupe_window_seconds=1,
            now=0.0,
        )
        self.guard.claim(
            "event-old-2",
            "room-old",
            limit=10,
            rate_window_seconds=3600,
            dedupe_window_seconds=1,
            now=1.0,
        )

        self.guard.claim(
            "event-current",
            "room-current",
            limit=10,
            rate_window_seconds=3600,
            dedupe_window_seconds=1,
            now=3602.0,
        )

        # No public outcome distinguishes old rate-history retention, so this
        # narrow state assertion protects the bounded-memory requirement.
        self.assertNotIn("room-old", self.guard._accepted_at_by_room)
        self.assertEqual([3602.0], self.guard._accepted_at_by_room["room-current"])

    def test_rate_window_cannot_exceed_retention_bound(self) -> None:
        with self.assertRaises(ValueError):
            self.guard.claim(
                "event-1",
                "room-1",
                limit=1,
                rate_window_seconds=3601,
                dedupe_window_seconds=1,
                now=100.0,
            )

    def test_later_short_dedupe_window_does_not_remove_long_lived_event(self) -> None:
        self.guard.claim(
            "event-long",
            "room-1",
            limit=10,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=100.0,
        )
        self.guard.claim(
            "event-short",
            "room-1",
            limit=10,
            rate_window_seconds=60,
            dedupe_window_seconds=1,
            now=102.0,
        )

        outcome = self.guard.claim(
            "event-long",
            "room-1",
            limit=10,
            rate_window_seconds=60,
            dedupe_window_seconds=1,
            now=103.0,
        )

        self.assertEqual("duplicate", outcome)

    def test_invalid_bounds_raise_before_pruning_existing_events(self) -> None:
        self.guard.claim(
            "event-long",
            "room-1",
            limit=10,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=100.0,
        )

        with self.assertRaises(ValueError):
            self.guard.claim(
                "event-invalid",
                "room-1",
                limit=0,
                rate_window_seconds=60,
                dedupe_window_seconds=120,
                now=1000.0,
            )

        outcome = self.guard.claim(
            "event-long",
            "room-1",
            limit=10,
            rate_window_seconds=60,
            dedupe_window_seconds=120,
            now=101.0,
        )

        self.assertEqual("duplicate", outcome)

    def test_each_positive_bound_is_required(self) -> None:
        invalid_arguments = (
            {"limit": 0, "rate_window_seconds": 60, "dedupe_window_seconds": 120},
            {"limit": 1, "rate_window_seconds": 0, "dedupe_window_seconds": 120},
            {"limit": 1, "rate_window_seconds": 60, "dedupe_window_seconds": 0},
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.guard.claim("event-1", "room-1", now=100.0, **arguments)


if __name__ == "__main__":
    unittest.main()
