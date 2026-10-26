"""Text channel: a terminal chat running the same pipeline as voice, minus STT/TTS."""

import asyncio
import random
import uuid
from pathlib import Path
from typing import Any

from pipecat.frames.frames import ErrorFrame, LLMMessagesTransformFrame
from pipecat.workers.runner import WorkerRunner

from voice_agent.config import Settings
from voice_agent.db.connection import connect
from voice_agent.dialogue.prompt import is_state_message, state_message
from voice_agent.dialogue.state import ConversationState
from voice_agent.domain.clock import SystemClock
from voice_agent.domain.ids import IdGenerator
from voice_agent.pipeline.bot import build_text_worker
from voice_agent.tools.handlers import ToolContext
from voice_agent.tools.registry import parse_faults

QUIT_WORDS = {"quit", "exit"}


async def run_chat(settings: Settings, db_path: Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"{db_path} not found. Run: uv run python -m voice_agent.db.seed --reset")
    clock = SystemClock()
    state = ConversationState(conversation_id=f"text-{uuid.uuid4().hex[:8]}")
    ctx = ToolContext(
        conn=connect(db_path),
        clock=clock,
        ids=IdGenerator(random.Random()),
        state=state,
        tool_timeout_secs=settings.tool_timeout_secs,
        faults=parse_faults(settings.fault_injection),
    )
    worker, output, guard = build_text_worker(
        settings, ctx, on_text=lambda text: print(text, end="", flush=True)
    )
    started = asyncio.Event()

    @worker.event_handler("on_pipeline_started")
    async def on_started(worker: object, frame: object) -> None:  # pyright: ignore[reportUnusedFunction]
        started.set()

    @worker.event_handler("on_pipeline_error")
    async def on_error(worker: object, frame: ErrorFrame) -> None:  # pyright: ignore[reportUnusedFunction]
        print(f"\n[pipeline error: {frame.error}]", flush=True)
        output.reply_done.set()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run_task = asyncio.create_task(runner.run())
    await started.wait()
    print(f"Osteria Verde text chat ({state.conversation_id}). Type 'quit' to leave.\n")

    try:
        while not state.ended:
            user_text = (await asyncio.to_thread(input, "you> ")).strip()
            if not user_text:
                continue
            if user_text.lower() in QUIT_WORDS:
                break
            state.start_turn()
            output.reply_done.clear()

            def add_turn(messages: list[Any], text: str = user_text) -> list[Any]:
                kept = [m for m in messages if not is_state_message(m)]
                return [*kept, state_message(state, clock), {"role": "user", "content": text}]

            print("bot> ", end="", flush=True)
            await worker.queue_frame(LLMMessagesTransformFrame(transform=add_turn, run_llm=True))
            try:
                await asyncio.wait_for(output.reply_done.wait(), settings.chat_reply_timeout_secs)
            except TimeoutError:
                print("[no reply: timed out, see logs]", end="")
            print("\n")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        await worker.end()
        await run_task
        ctx.conn.close()
        print(f"guard.triggered: {guard.triggered_count}")
