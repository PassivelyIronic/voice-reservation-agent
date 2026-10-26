"""E5: the LLM switcher moves to the next provider on 429s/outages, not only on dead keys."""

from pipecat.frames.frames import ErrorFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.utils.errors import ErrorCategory

from voice_agent.providers.llm import FailoverOnTransientErrors


def strategy() -> tuple[FailoverOnTransientErrors, FrameProcessor, FrameProcessor]:
    primary, backup = FrameProcessor(name="groq"), FrameProcessor(name="gemini")
    return FailoverOnTransientErrors([primary, backup]), primary, backup


async def test_rate_limit_switches_to_backup() -> None:
    s, primary, backup = strategy()
    switched = await s.handle_error(
        ErrorFrame(error="429", processor=primary, category=ErrorCategory.RATE_LIMIT)
    )
    assert switched is backup
    assert s.active_service is backup


async def test_server_error_switches_to_backup() -> None:
    s, primary, backup = strategy()
    error = ErrorFrame(error="503", processor=primary, category=ErrorCategory.SERVER)
    assert await s.handle_error(error) is backup


async def test_invalid_request_does_not_switch() -> None:
    s, primary, _ = strategy()
    error = ErrorFrame(error="bad", processor=primary, category=ErrorCategory.INVALID_REQUEST)
    assert await s.handle_error(error) is None
    assert s.active_service is primary
