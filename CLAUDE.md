# CLAUDE.md — Voice Reservation Agent

Real-time voice agent for a fictional restaurant (Osteria Verde): table reservations + menu/allergen questions.
Pipecat cascade pipeline: Silero VAD + Smart Turn v3 → faster-whisper → LLM with tools (Groq, failover Gemini/Ollama)
→ AllergenClaimGuard → Kokoro TTS, over SmallWebRTC. SQLite. Zero-cost stack.

## Source of truth
- Plan: `docs/plan/README.md` (index). Specs: `04-data-model.md`, `05-tools-spec.md`, `06-dialogue-guardrails.md`, `07-evaluation.md`.
- Current milestone and Definition of Done: `docs/plan/08-roadmap.md`. Work on one milestone at a time.
- Decisions: `docs/plan/adr/`. If implementation must deviate from a spec, stop and propose a new ADR first.

## Scope discipline
This is one of several portfolio projects. Build exactly the current milestone's DoD in `08-roadmap.md`.
Do not add features, abstractions, providers or config options that the DoD does not require.
M7 items are optional and start only when I explicitly ask. Prefer the simplest implementation that passes the DoD.

## baseline/ (M3.5)
A deliberately naive, from-scratch voice loop used only as a measured reference. No Pipecat imports.
It reuses `voice_agent.tools`, `voice_agent.dialogue` and the guard. Hard limit ~300 lines. Frozen after measurement:
do not improve it later (that would invalidate the comparison).

## Pipecat API — never from memory
Pipecat 1.x changes fast (frequent releases, renamed classes, deprecations).
- When the `pipecat-context-hub` MCP is available, always prefer its tools (`search_docs`, `search_api`,
  `search_examples`, `get_example`, `get_doc`, `get_code_snippet`, `check_deprecation`) for any Pipecat question.
- Run `check_deprecation` on every Pipecat import you add. Record non-obvious API findings in `docs/notes/pipecat-api-notes.md` with links.
- Fallback: https://docs.pipecat.ai/llms.txt

## Architecture rules (hard)
1. Layering: `channels → pipeline → dialogue → tools → domain → db`. `domain/` must not import pipecat or any LLM SDK.
2. Tool handlers are thin adapters; business rules live in `domain/`. Tool results use the envelope `{ok, data | error{code, agent_hint, retryable}}`.
3. Customer-facing precise text (readback, allergen `spoken_answer`) comes from `dialogue/renderers.py` templates, never LLM paraphrase.
4. Allergen answers come only from `menu_item_allergens`. Missing row = UNKNOWN. Never default to FREE.
5. `create_reservation` only accepts a `hold_id`; returns `CONFIRMATION_REQUIRED` if the hold was created in the same user turn.
6. `AllergenClaimGuard` sits between LLM and TTS in every pipeline variant (voice, text, eval). Never bypass it, including in tests of the full pipeline.
7. Model IDs, API keys, thresholds, timeouts: config only (`config.py`, `.env`, `evals/thresholds.yaml`). No hardcoding.
8. Time comes from the injected `Clock`. No `datetime.now()` outside `domain/clock.py`.

## Evaluation rules (hard)
- NEVER lower a value in `evals/thresholds.yaml`, loosen a matcher, delete/skip a failing scenario, or edit a cassette by hand to make evals pass. Report the failure and propose a fix or an ADR instead.
- `allergen_hallucinations_spoken == 0` is a non-negotiable gate.
- Changing prompt/tools invalidates cassettes: re-record in live mode, commit with the change.
- No unverified claims: README numbers are generated from `evals/reports/`; never type metrics by hand.
- No hidden mock mode. Any mock/replay mode must be explicit in CLI flags and documented.

## Commands
```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q                                   # unit + integration (no network)
uv run python -m voice_agent.db.seed --reset       # rebuild local DB
uv run python -m voice_agent.db.seed --check       # validate seed data
uv run voice-agent chat  --profile cloud           # text mode (M2+)
uv run voice-agent voice --profile cloud           # voice mode (M4+), open printed URL
uv run python baseline/naive_loop.py               # naive baseline (M3.5)
uv run python -m evals.run --suite all --mode replay   # CI mode (M3+)
uv run python -m evals.run --suite core --mode live    # uses free-tier quota; keep runs small
```

## Conventions
- Python 3.12, type hints everywhere, Pydantic v2 models at boundaries, `async` in pipeline code.
- Tests first for domain rules and the guard. Unit tests must not hit the network.
- Logging: loguru; per-turn metrics as JSON lines to `logs/turns.jsonl`. Never log API keys.
- Commits: `M<n>: <imperative summary>`. Keep PR-sized changes.
- Free-tier awareness: avoid live eval loops; batch live runs; prefer replay.
- Data is fictional. Never add real personal data or real restaurant allergen data.

## Definition of Done (every task)
ruff + pyright + pytest green; replay evals green (from M3); roadmap status updated; new decisions captured as ADR; docs updated if behavior changed.
