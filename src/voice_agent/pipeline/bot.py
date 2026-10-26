"""Pipeline assembly. Text mode: no transport, STT or TTS; the guard still sits after the LLM."""

import asyncio
from collections.abc import Awaitable, Callable

from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import (
    Frame,
    FunctionCallsStartedFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.llm_service import FunctionCallParams

from voice_agent.config import Settings
from voice_agent.dialogue.prompt import build_system_prompt
from voice_agent.guards.allergen_guard import AllergenClaimGuard
from voice_agent.providers.llm import build_llm
from voice_agent.tools.handlers import ToolContext
from voice_agent.tools.registry import run_tool
from voice_agent.tools.schemas import TOOL_SPECS


def build_tools(ctx: ToolContext) -> list[FunctionSchema]:
    def handler(name: str) -> Callable[[FunctionCallParams], Awaitable[None]]:
        async def handle(params: FunctionCallParams) -> None:
            await params.result_callback(await run_tool(ctx, name, dict(params.arguments)))

        return handle

    return [
        FunctionSchema(
            name=spec.name,
            description=spec.description,
            properties=spec.properties,
            required=spec.required,
            handler=handler(spec.name),
        )
        for spec in TOOL_SPECS
    ]


class TextOutput(FrameProcessor):
    """Collects the bot's (guarded) text and signals when a reply is complete.

    A response that starts function calls is followed by another LLM response with the
    results, so only a response without function calls ends the bot's turn.
    """

    def __init__(self, on_text: Callable[[str], None]) -> None:
        super().__init__()
        self._on_text = on_text
        self._calls_started = False
        self.reply_done = asyncio.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, LLMTextFrame):
                self._on_text(frame.text)
            elif isinstance(frame, FunctionCallsStartedFrame):
                self._calls_started = True
            elif isinstance(frame, LLMFullResponseEndFrame):
                if self._calls_started:
                    self._calls_started = False
                else:
                    self.reply_done.set()
        await self.push_frame(frame, direction)


def build_text_worker(
    settings: Settings, ctx: ToolContext, on_text: Callable[[str], None]
) -> tuple[PipelineWorker, TextOutput, AllergenClaimGuard]:
    context = LLMContext(tools=build_tools(ctx))  # type: ignore[arg-type]
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)
    llm = build_llm(settings, build_system_prompt(ctx.clock))
    guard = AllergenClaimGuard(approved=ctx.state.approved_sentences)
    output = TextOutput(on_text)
    pipeline = Pipeline([user_aggregator, llm, guard, output, assistant_aggregator])
    worker = PipelineWorker(pipeline, enable_rtvi=False)
    return worker, output, guard
