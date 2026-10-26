---
title: Voice Reservation Agent — plan projektu
tags: [portfolio, voice-ai, plan, moc]
status: planning
updated: 2026-10-26
---

# Voice Reservation Agent — plan projektu (MOC)

Głosowy agent restauracji „Osteria Verde” (fikcyjna): rezerwacje stolików + pytania o menu/alergeny, w czasie rzeczywistym, z tool callingiem, twardym guardrailem na alergenach i mierzalną ewaluacją. **Koszt: 0 zł** (open source + lokalne modele + darmowe tiery API).

> [!NOTE]
> Pliki działają w Obsidianie (vault = ten folder) i na GitHubie: zwykłe linki względne, frontmatter YAML, diagramy Mermaid, callouty `> [!NOTE]`. Żadne pluginy Obsidiana nie są wymagane.

## Mapa dokumentów

| # | Dokument | Zawartość |
|---|---|---|
| 1 | [Brief](01-brief.md) | Cel, zakres, non-goals, kryteria sukcesu |
| 2 | [Architektura](02-architecture.md) | Diagramy, warstwy, przepływ tury, latency budget |
| 3 | [Tech stack](03-tech-stack.md) | Wybory + uzasadnienie, darmowe tiery, licencje, VRAM |
| 4 | [Model danych](04-data-model.md) | Schemat SQL, alergeny, sloty, seed + prompt do generacji |
| 5 | [Specyfikacja narzędzi](05-tools-spec.md) | Tool definitions (JSON Schema), kontrakty, błędy |
| 6 | [Dialog i guardrails](06-dialogue-guardrails.md) | System prompt, guard alergenów, handoff, edge cases |
| 7 | [Ewaluacja](07-evaluation.md) | Metryki, scenariusze, harness, progi, CI gate |
| 8 | [Roadmapa](08-roadmap.md) | Rdzeń vs opcje, time-boxy, M0–M7, gotowe prompty do Claude Code |
| 9 | [Prezentacja w portfolio](09-portfolio-presentation.md) | README docelowe, demo video, checklisty |
| — | [ADR](adr/README.md) | Decyzje architektoniczne (0001–0006) |
| — | [CLAUDE.md](../../CLAUDE.md) | Instrukcje dla Claude Code (kopiowane do root repo) |

## Decyzje w jednym zdaniu

- **Framework:** Pipecat (BSD-2) + `SmallWebRTCTransport` (P2P, bez serwera mediów) → [ADR-0001](adr/0001-pipecat-over-livekit.md)
- **Architektura:** kaskada STT → LLM(tools) → guard → TTS, nie speech-to-speech → [ADR-0002](adr/0002-cascaded-pipeline.md)
- **Modele:** STT faster-whisper lokalnie (GPU), LLM Groq free tier (fallback: Gemini Flash / Ollama), TTS Kokoro lokalnie → [ADR-0003](adr/0003-model-providers.md)
- **Stan i bezpieczeństwo:** logika biznesowa deterministyczna (SQL + Python), LLM tylko NLU + dialog → [ADR-0004](adr/0004-deterministic-core.md)
- **Baza:** SQLite, model slotowy z `UNIQUE` zamiast exclusion constraints → [ADR-0005](adr/0005-sqlite-slot-model.md)
- **Ewaluacja:** text-mode harness (asercje na stanie DB) + Pipecat Evals (audio) → [ADR-0006](adr/0006-two-level-evaluation.md)
- **Baseline od zera (M3.5):** ~300 linii FastAPI + WebSocket bez frameworka, zmierzony obok Pipecata → dowód dla ADR-0001
- **Zakres:** rdzeń ≈ 11 dni, reszta opcjonalna; cięcie awaryjne ≈ 8 dni → [Roadmapa](08-roadmap.md#zasada-anty-overkill)

## Jak użyć z Claude Code

1. Rozpakuj paczkę do root nowego repo: `CLAUDE.md` ląduje w root, plan w `docs/plan/` (ścieżki w CLAUDE.md i promptach już na to wskazują).
2. Zainstaluj Pipecat Context Hub jako MCP (aktualna dokumentacja API zamiast pamięci modelu):
   ```bash
   uvx pipecat-ai-context-hub@latest refresh
   claude mcp add pipecat-context-hub -- uvx pipecat-ai-context-hub serve
   ```
3. Realizuj milestone po milestone wg [Roadmapy](08-roadmap.md) — każdy ma gotowy prompt startowy. Na początku każdego milestone'u używaj plan mode.
4. Po każdym milestonie: `uv run pytest`, `uv run python -m evals.run --mode replay`, aktualizacja statusu w roadmapie.
