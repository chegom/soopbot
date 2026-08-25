"""Stateless trigger handling and reply generation for Soopbot."""

from dataclasses import dataclass
import logging
from typing import Literal, Protocol

from soopbot.config import Settings


logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 4000
_INTRODUCTION = "안녕하세요, 숲봇이에요.\n궁금한 점을 이어서 말해 주세요.\n짧고 친절하게 답해 드릴게요."


class ReplyProvider(Protocol):
    def generate(self, *, persona: str, question: str) -> str: ...


@dataclass(frozen=True)
class ReplyOutcome:
    kind: Literal["no_trigger", "reply", "provider_failure"]
    content: str = ""


def extract_question(content: str, trigger: str) -> str | None:
    """Return text after the first literal trigger, if present."""
    index = content.find(trigger)
    if index == -1:
        return None
    return content[index + len(trigger) :].lstrip(" \t\r\n:：,，.-—–")


class ReplyService:
    def __init__(self, settings: Settings, provider: ReplyProvider) -> None:
        self._settings = settings
        self._provider = provider

    def handle(self, content: str) -> ReplyOutcome:
        if len(content) >= _MAX_INPUT_CHARS:
            raise ValueError("message must be fewer than 4000 characters")

        question = extract_question(content, self._settings.trigger)
        if question is None:
            return ReplyOutcome("no_trigger")
        if not question:
            return ReplyOutcome("reply", _INTRODUCTION)

        try:
            reply = self._provider.generate(
                persona=self._settings.persona, question=question
            )
        except Exception as error:
            logger.warning("provider_failure error_type=%s", type(error).__name__)
            return ReplyOutcome(
                "provider_failure",
                "지금은 답변을 만들지 못했어요. 잠시 후 숲봇을 다시 불러 주세요.",
            )

        return ReplyOutcome("reply", reply[: self._settings.max_output_chars])
