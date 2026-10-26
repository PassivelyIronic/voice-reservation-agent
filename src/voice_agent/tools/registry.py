"""Run tool handlers with timeouts, one retry on a locked DB and optional fault injection.

FAULT_INJECTION="check_availability:error:1.0,search_menu:timeout:0.3" makes the named tools
fail (or exceed the timeout) with the given probability, drawn from a seeded RNG.
"""

import asyncio
import json
import sqlite3
from typing import Any

from loguru import logger

from voice_agent.domain.errors import DomainError, ErrorCode
from voice_agent.tools.handlers import HANDLERS, Envelope, ToolContext, error, error_details
from voice_agent.tools.schemas import TOOL_SPECS

DB_LOCKED_RETRY_DELAY_SECS = 0.1


class InjectedFault(Exception):
    pass


def parse_faults(spec: str) -> dict[str, tuple[str, float]]:
    faults: dict[str, tuple[str, float]] = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, kind, probability = part.split(":")
        if name not in HANDLERS or kind not in ("error", "timeout"):
            raise ValueError(f"Invalid FAULT_INJECTION entry: {part!r}")
        faults[name] = (kind, float(probability))
    return faults


def _call(ctx: ToolContext, name: str, args: dict[str, Any]) -> Envelope:
    try:
        return HANDLERS[name](ctx, args)
    except DomainError as exc:
        return error(exc.code, error_details(exc))


async def run_tool(ctx: ToolContext, name: str, args: dict[str, Any]) -> Envelope:
    """Execute one tool call and always return an envelope (never raise)."""

    async def attempt() -> Envelope:
        fault = ctx.faults.get(name)
        if fault and ctx.fault_rng.random() < fault[1]:
            if fault[0] == "timeout":
                await asyncio.sleep(ctx.tool_timeout_secs * 2)
            raise InjectedFault(f"injected {fault[0]} in {name}")
        try:
            return _call(ctx, name, args)
        except sqlite3.OperationalError:
            await asyncio.sleep(DB_LOCKED_RETRY_DELAY_SECS)
            return _call(ctx, name, args)

    try:
        result = await asyncio.wait_for(attempt(), timeout=ctx.tool_timeout_secs)
    except Exception as exc:  # timeout, injected fault, unexpected bug: the LLM gets an envelope
        logger.warning(f"tool {name} failed: {exc!r}")
        result = error(ErrorCode.TOOL_ERROR)
    logger.info(f"tool {name} args={json.dumps(args)} result={json.dumps(result)}")
    return result


def tool_names() -> list[str]:
    return [spec.name for spec in TOOL_SPECS]
