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
    async def handle_error(self, error: ErrorFrame) -> FrameProcessor | None:
        switched = await super().handle_error(error)
        if switched is not None or error.category not in TRANSIENT_CATEGORIES:
            return switched
        active = self.active_service
        if active is None:
            return None
        current = self.services.index(active)
        for offset in range(1, len(self.services)):
            candidate = self.services[(current + offset) % len(self.services)]
            if candidate.is_usable:
                logger.warning(f"LLM failover after {error.category.name}: -> {candidate.name}")
                return await self._set_active_if_available(candidate)
        return None


def build_llm(settings: Settings, system_instruction: str) -> LLMSwitcher:
    if settings.groq_api_key is None or not settings.groq_agent_model:
        raise RuntimeError("GROQ_API_KEY and GROQ_AGENT_MODEL must be set (see .env.example).")
    llms: list[LLMService[Any]] = [
        GroqLLMService(
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
