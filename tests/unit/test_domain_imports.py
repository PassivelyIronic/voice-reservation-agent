"""DoD M1: domain/ must not import Pipecat or any LLM client."""

import ast
from pathlib import Path

import voice_agent.domain

FORBIDDEN = {"pipecat", "openai", "groq", "google", "ollama", "anthropic"}
DOMAIN_DIR = Path(voice_agent.domain.__file__).parent


def test_domain_has_no_framework_or_llm_imports() -> None:
    offenders: list[str] = []
    for path in DOMAIN_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in FORBIDDEN]
    assert offenders == []
