import unittest

from soopbot.config import Settings


class SettingsTest(unittest.TestCase):
    def valid_environment(self) -> dict[str, str]:
        return {
            "OPENAI_API_KEY": "test-openai-key",
            "SOOPBOT_TOKEN": "t" * 24,
        }

    def test_defaults_are_safe_and_publicly_documented(self) -> None:
        settings = Settings.from_environ(self.valid_environment())

        self.assertEqual("숲봇아", settings.trigger)
        self.assertEqual("room1", settings.room_key)
        self.assertEqual("gpt-5.6-luna", settings.model)
        self.assertEqual(1000, settings.max_output_chars)
        self.assertEqual(10, settings.requests_per_minute)

    def test_secret_values_are_not_exposed_by_repr(self) -> None:
        settings = Settings.from_environ(self.valid_environment())

        rendered = repr(settings)

        self.assertNotIn("test-openai-key", rendered)
        self.assertNotIn("t" * 24, rendered)

    def test_required_secrets_and_bounds_are_rejected(self) -> None:
        invalid_cases = [
            ({"OPENAI_API_KEY": "", "SOOPBOT_TOKEN": "t" * 24}, "OPENAI_API_KEY"),
            ({"OPENAI_API_KEY": "key", "SOOPBOT_TOKEN": "short"}, "SOOPBOT_TOKEN"),
            (
                {
                    **self.valid_environment(),
                    "SOOPBOT_REQUESTS_PER_MINUTE": "0",
                },
                "SOOPBOT_REQUESTS_PER_MINUTE",
            ),
        ]

        for environment, expected_name in invalid_cases:
            with self.subTest(expected_name):
                with self.assertRaisesRegex(ValueError, expected_name):
                    Settings.from_environ(environment)
