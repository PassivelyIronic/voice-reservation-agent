"""E5: the LLM switcher moves to the next provider on 429s/outages, not only on dead keys."""

from pipecat.frames.frames import (
    ErrorFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.groq.llm import GroqLLMService
from pipecat.tests.utils import run_test
from pipecat.utils.errors import ErrorCategory

from voice_agent.pipeline.bot import TextOutput
from voice_agent.providers.llm import FailoverOnTransientErrors, GroqWithoutClientRetries


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


async def test_switch_requests_a_rerun_of_the_failed_turn() -> None:
    s, primary, _ = strategy()
    await s.handle_error(ErrorFrame(error="429", processor=primary, category=ErrorCategory.QUOTA))
    assert s.rerun_needed


async def test_silent_failed_response_is_rerun_not_ended() -> None:
    s, _, _ = strategy()
    s.rerun_needed = True
    output = TextOutput(on_text=lambda _: None, failover=s)
    down, _ = await run_test(
        output, frames_to_send=[LLMFullResponseStartFrame(), LLMFullResponseEndFrame()]
    )
    assert isinstance(down[-1], LLMRunFrame)
    assert not output.reply_done.is_set()
    assert not s.rerun_needed


async def test_response_with_text_is_not_rerun_after_a_switch() -> None:
    s, _, _ = strategy()
    s.rerun_needed = True
    output = TextOutput(on_text=lambda _: None, failover=s)
    frames = [LLMFullResponseStartFrame(), LLMTextFrame("Hello."), LLMFullResponseEndFrame()]
    down, _ = await run_test(output, frames_to_send=frames)
    assert not any(isinstance(f, LLMRunFrame) for f in down)
    assert output.reply_done.is_set()


def test_groq_client_does_not_retry_on_its_own() -> None:
    llm = GroqWithoutClientRetries(
        max_retries=0, api_key="test", settings=GroqLLMService.Settings(model="m")
    )
    assert llm._client.max_retries == 0  # pyright: ignore[reportPrivateUsage]
