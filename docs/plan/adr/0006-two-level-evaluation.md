---
title: "ADR-0006: Dwupoziomowa ewaluacja"
status: accepted
date: 2026-10-26
tags: [adr]
---

# ADR-0006: Ewaluacja text (L1) + audio (L2)

## Kontekst
Ewaluacja głosowa jest wolna i kosztowna; większość błędów to błędy dialogu/narzędzi, niezależne od audio. Free tier LLM ma dzienne limity tokenów. CI nie ma GPU.

## Decyzja
- **L1 (text):** własny harness uruchamiający **ten sam pipeline** w trybie tekstowym; asercje na stanie bazy i wywołaniach narzędzi; tryb replay z kasetami w CI; bramki z `thresholds.yaml`.
- **L2 (audio):** Pipecat Evals (lokalny Kokoro jako głos klienta, lokalny Whisper/Ollama jako sędzia) + benchmark STT/slot error rate + pomiar latencji; uruchamiane lokalnie.

## Fallback (jeśli tryb tekstowy pipeline'u okaże się niepraktyczny w spike M2)
Harness L1 wywołuje LLM bezpośrednio przez klienta OpenAI-compatible z **tymi samymi** definicjami narzędzi, system promptem, handlerami i guardem (współdzielone moduły `tools/`, `dialogue/`, `guards/`). Różnica względem pipeline'u (agregacja kontekstu) dokumentowana w README jako ograniczenie.

## Dlaczego własny harness obok Pipecat Evals
Pipecat Evals ocenia zdarzenia i wypowiedzi bota; definicja „task completed” w tym projekcie to **stan bazy** (rezerwacja z właściwymi polami, ticket handoffu z właściwym `reason`) oraz metryki allergen guard — tego potrzebuje własna warstwa asercji.

## Konsekwencje
- (+) Szybkie, darmowe, deterministyczne CI.
- (−) Kasety wymagają ponownego nagrania po zmianie promptu/narzędzi — świadomie (zmiana zachowania = zmiana testu).
