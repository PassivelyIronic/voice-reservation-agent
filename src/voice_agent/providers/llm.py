"""LLM services (Groq, then Gemini) behind an LLMSwitcher that also fails over on 429s/outages."""

from typing import Any

from loguru import logger
from pipecat.frames.frames import ErrorFrame
from pipecat.pipeline.llm_switcher import LLMSwitcher
from pipecat.pipeline.service_switcher import ServiceSwitcherStrategyFailover
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import LLMService
from pipecat.utils.errors import ErrorCategory

from voice_agent.config import Settings

# Transient provider failures worth moving to the next provider for (E5). The built-in
# strategy only fails over when a service becomes unusable (bad key, unknown model).
TRANSIENT_CATEGORIES = frozenset(
    {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.QUOTA,
        ErrorCategory.CONNECTIVITY,
        ErrorCategory.SERVER,
    }
)


class FailoverOnTransientErrors(ServiceSwitcherStrategyFailover):
    """Failover strategy that also switches on transient errors.

    The failed request is not re-sent by Pipecat, so a switch sets `rerun_needed`; the output
    processor then re-runs the LLM on the same context if the failed response said nothing.
    """

    rerun_needed: bool = False

    async def handle_error(self, error: ErrorFrame) -> FrameProcessor | None:
        switched = await super().handle_error(error) or await self._switch_on_transient(error)
        if switched is not None:
            self.rerun_needed = True
        return switched

    async def _switch_on_transient(self, error: ErrorFrame) -> FrameProcessor | None:
        active = self.active_service
        if active is None or error.category not in TRANSIENT_CATEGORIES:
            return None
        current = self.services.index(active)
        for offset in range(1, len(self.services)):
            candidate = self.services[(current + offset) % len(self.services)]
            if candidate.is_usable:
                logger.warning(f"LLM failover after {error.category.name}: -> {candidate.name}")
                return await self._set_active_if_available(candidate)
        return None


class GroqWithoutClientRetries(GroqLLMService):
    """Groq service whose OpenAI client does not retry on its own.

    By default the client retries a 429 twice, honouring Groq's retry-after (~10 s on the free
    tier), so Pipecat only sees the error 20-30 s later and the failover comes too late.
    """

    def __init__(self, *, max_retries: int, **kwargs: Any) -> None:
        self._max_retries = max_retries
        super().__init__(**kwargs)

    def create_client(self, api_key: Any = None, base_url: Any = None, **kwargs: Any) -> Any:
        client = super().create_client(api_key, base_url, **kwargs)
        return client.with_options(max_retries=self._max_retries)


def build_llm(
    settings: Settings, system_instruction: str
) -> LLMSwitcher[FailoverOnTransientErrors]:
    if settings.groq_api_key is None or not settings.groq_agent_model:
        raise RuntimeError("GROQ_API_KEY and GROQ_AGENT_MODEL must be set (see .env.example).")
    llms: list[LLMService[Any]] = [
        GroqWithoutClientRetries(
            max_retries=settings.groq_max_retries,
            api_key=settings.groq_api_key.get_secret_value(),
            settings=GroqLLMService.Settings(
                model=settings.groq_agent_model, system_instruction=system_instruction
            ),
        )
    ]
    if settings.gemini_api_key is not None and settings.gemini_model:
        llms.append(
            GoogleLLMService(
                api_key=settings.gemini_api_key.get_secret_value(),
                settings=GoogleLLMService.Settings(
                    model=settings.gemini_model, system_instruction=system_instruction
                ),
            )
        )
    else:
        logger.warning("GEMINI_API_KEY/GEMINI_MODEL not set: running without an LLM fallback.")
    switcher = LLMSwitcher(llms=llms, strategy_type=FailoverOnTransientErrors)

    @switcher.strategy.event_handler("on_service_switched")
    async def on_service_switched(strategy: object, service: FrameProcessor) -> None:  # pyright: ignore[reportUnusedFunction]
        logger.warning(f"llm.switched active={service.name}")

    return switcher
