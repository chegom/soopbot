"""Validated runtime settings for Soopbot."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    bot_token: str = field(repr=False)
    trigger: str
    persona: str
    room_key: str
    model: str
    max_output_chars: int
    max_output_tokens: int
    timeout_seconds: int
    requests_per_minute: int
    max_history_turns: int = 4

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ

        openai_api_key = _required_text(values, "OPENAI_API_KEY", maximum=512)
        bot_token = load_bot_token(values)

        return cls(
            openai_api_key=openai_api_key,
            bot_token=bot_token,
            trigger=_text(values, "SOOPBOT_TRIGGER", "숲봇아", maximum=100),
            persona=_text(
                values,
                "SOOPBOT_PERSONA",
                "친절하고 간결한 카카오톡 AI 도우미 숲봇으로 답하세요.",
                maximum=1000,
            ),
            room_key=_text(values, "SOOPBOT_ROOM_KEY", "room1", maximum=100),
            model=_text(values, "OPENAI_MODEL", "gpt-5.6-luna", maximum=200),
            max_output_chars=_integer(
                values, "SOOPBOT_MAX_OUTPUT_CHARS", 1000, minimum=100, maximum=4000
            ),
            max_output_tokens=_integer(
                values, "SOOPBOT_MAX_OUTPUT_TOKENS", 500, minimum=1, maximum=4000
            ),
            timeout_seconds=_integer(
                values, "SOOPBOT_TIMEOUT_SECONDS", 40, minimum=1, maximum=120
            ),
            requests_per_minute=_integer(
                values, "SOOPBOT_REQUESTS_PER_MINUTE", 10, minimum=1, maximum=120
            ),
            max_history_turns=_integer(
                values, "SOOPBOT_MAX_HISTORY_TURNS", 4, minimum=0, maximum=10
            ),
        )


def load_bot_token(environ: Mapping[str, str] | None = None) -> str:
    """Load only the credential needed to authenticate an inbound request."""
    values = os.environ if environ is None else environ
    bot_token = _required_text(values, "SOOPBOT_TOKEN", maximum=512)
    if len(bot_token) < 24:
        raise ValueError("SOOPBOT_TOKEN must be at least 24 characters")
    return bot_token


def _required_text(values: Mapping[str, str], name: str, maximum: int) -> str:
    value = _text(values, name, "", maximum=maximum)
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _text(values: Mapping[str, str], name: str, default: str, maximum: int) -> str:
    value = values.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value


def _integer(
    values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int
) -> int:
    raw_value = values.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value
