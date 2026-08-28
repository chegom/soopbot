import unittest

from soopbot.conversation import HISTORY_TTL_SECONDS, MemoryConversationLog, Turn


class MemoryConversationLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.log = MemoryConversationLog()

    def test_recorded_turns_come_back_oldest_first(self) -> None:
        self.log.record("질문1", "답변1", now=100.0)
        self.log.record("질문2", "답변2", now=101.0)

        self.assertEqual(
            (Turn("질문1", "답변1"), Turn("질문2", "답변2")),
            self.log.recent(limit=4, now=102.0),
        )

    def test_only_the_newest_turns_are_returned(self) -> None:
        for index in range(1, 5):
            self.log.record(f"질문{index}", f"답변{index}", now=100.0 + index)

        self.assertEqual(
            (Turn("질문3", "답변3"), Turn("질문4", "답변4")),
            self.log.recent(limit=2, now=110.0),
        )

    def test_turns_older_than_the_ttl_are_forgotten(self) -> None:
        self.log.record("오래된 질문", "오래된 답변", now=100.0)
        self.log.record("최근 질문", "최근 답변", now=100.0 + HISTORY_TTL_SECONDS)

        recent = self.log.recent(limit=4, now=100.0 + HISTORY_TTL_SECONDS + 1)

        self.assertEqual((Turn("최근 질문", "최근 답변"),), recent)

    def test_zero_limit_returns_no_context(self) -> None:
        self.log.record("질문", "답변", now=100.0)

        self.assertEqual((), self.log.recent(limit=0, now=101.0))

    def test_log_never_grows_beyond_its_capacity(self) -> None:
        for index in range(200):
            self.log.record(f"질문{index}", f"답변{index}", now=100.0 + index)

        self.assertLessEqual(self.log.size(), MemoryConversationLog.MAX_TURNS)


if __name__ == "__main__":
    unittest.main()
