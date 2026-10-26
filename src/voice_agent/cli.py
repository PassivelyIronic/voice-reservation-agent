"""voice-agent command line: `voice-agent chat --profile cloud`."""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from voice_agent.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    chat = sub.add_parser("chat", help="text chat with the agent (same pipeline, no audio)")
    chat.add_argument("--profile", choices=["cloud", "cpu", "local"], default=None)
    chat.add_argument("--db", type=Path, default=None, help="database path (default: DB_PATH)")
    chat.add_argument("--verbose", action="store_true", help="show pipeline logs")
    args = parser.parse_args(argv)

    overrides = {"voice_profile": args.profile} if args.profile else {}
    settings = Settings(**overrides)  # type: ignore[arg-type]
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "WARNING")

    if args.command == "chat":
        from voice_agent.channels.text_cli import run_chat

        asyncio.run(run_chat(settings, args.db or settings.db_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
