---
title: Roadmapa i prompty do Claude Code
tags: [voice-ai, roadmap, claude-code]
updated: 2026-10-26
---

# 08 — Roadmapa

Kolejność: **domena → tekst → ewaluacja → baseline → głos → pomiary → prezentacja.** Głos dopiero w M4, bo błędy dialogu taniej łapać w tekście.

## Zasada anty-overkill

To jeden z kilku projektów portfolio. Rekruter spędzi w repo ~90 sekund i zobaczy: **wideo, diagram, tabelę wyników, sekcję „Does every part need an LLM?”, guard alergenów.** Wszystko, co tego nie zasila, jest opcjonalne.

- **Rdzeń (≈ 11 dni)** = projekt gotowy do CV. Robisz w całości.
- **Opcjonalne** = tylko jeśli projekt nadal Cię bawi i nie blokuje innych projektów portfolio. Każdy punkt jest niezależny.
- **Minimalne cięcie awaryjne (≈ 8 dni):** M0–M4 + skrócone M7 (README + wideo). Wtedy brak bramek audio, ale nadal pełny, uczciwy projekt.
- Time-boxy są twarde: po przekroczeniu o 50% — upraszczasz, nie dokładasz.

| M | Cel | Time-box | Tier | Status |
|---|---|---|---|---|
| M0 | Bootstrap repo, tooling, CI | 0.5 d | rdzeń | ✅ |
| M1 | Domena + DB + seed (bez LLM) | 1.5 d | rdzeń | ✅ |
| M2 | Narzędzia + agent tekstowy (CLI) + guard | 2 d | rdzeń | ✅ |
| M3 | Harness ewaluacyjny L1 + bramka CI | 1.5 d | rdzeń | ⬜ |
| M3.5 | Naiwny baseline od zera (punkt odniesienia dla Pipecata) | 1 d | rdzeń | ⬜ |
| M4 | Pipeline głosowy w Pipecacie | 2 d | rdzeń | ⬜ |
| M5 | Pomiary: latency, STT bench (+ linia telefoniczna 8 kHz), hardening | 1.5 d | rdzeń | ⬜ |
| M6 | Frontend (minimalny panel debug) + demo video + README | 1.5 d | rdzeń | ⬜ |
| M7 | Opcjonalne rozszerzenia (lista na dole, w kolejności wartości) | — | opcja | ⬜ |

## Docelowa struktura repo

```
voice-reservation-agent/
├── CLAUDE.md
├── README.md                      # EN, dla rekruterów (M6)
├── pyproject.toml                 # uv, ruff, pyright, pytest config
├── .env.example
├── docker-compose.yml             # bot (+gpu)
├── Dockerfile
├── .github/workflows/ci.yml       # lint, typecheck, unit, evals --mode replay
├── data/seed/                     # menu.yaml, tables.yaml, hours.yaml, info.yaml
├── src/voice_agent/
│   ├── config.py                  # pydantic-settings, profile cloud|cpu (|local opcjonalnie)
│   ├── domain/                    # clock, availability, reservations, menu, allergens, errors
│   ├── db/                        # schema.sql, connection.py, repository.py, seed.py
│   ├── tools/                     # schemas.py, handlers.py, registry.py (timeouts, faults)
│   ├── dialogue/                  # prompts/system.md, state.py, renderers.py
│   ├── guards/                    # allergen_guard.py (FrameProcessor), lexicon.py
│   ├── providers/                 # llm.py, stt.py, tts.py (fabryki + ServiceSwitcher)
│   ├── pipeline/                  # bot.py, processors/, observers/
│   ├── channels/                  # voice_webrtc.py, text_cli.py
│   └── api/                       # FastAPI: /api/offer, /healthz, /reservations
├── baseline/                      # M3.5: naiwna pętla od zera — zamrożona po pomiarze
│   ├── naive_loop.py
│   ├── static/index.html          # mikrofon → AudioWorklet → WebSocket
│   └── README.md                  # wyniki pomiaru + czego baseline nie umie
├── evals/
│   ├── scenarios/                 # L1 YAML
│   ├── audio/                     # scenarios/, stt_bench.py, recordings/
│   ├── harness/                   # runner, matchers, metrics, report, cassette
│   ├── cassettes/
│   ├── thresholds.yaml            # 🔒 chroniony
│   └── reports/
├── tests/{unit,integration}/
├── client/                        # minimalny frontend (M6)
├── scripts/                       # update_readme_metrics.py
└── docs/                          # plan, ADR, diagramy, zrzuty
```

---

## M0 — Bootstrap (0.5 d)
**DoD:** `uv sync` działa; `ruff`, `pyright`, `pytest` przechodzą na pustym szkielecie; CI zielone; pre-commit; `.env.example`; Pipecat Context Hub podpięty.

**Prompt:**
```text
Read CLAUDE.md and docs/plan/08-roadmap.md (M0) and docs/plan/03-tech-stack.md.
Bootstrap the repository per the "Docelowa struktura repo" tree (skip baseline/ and client/ for now):
uv project (Python 3.12), src layout package `voice_agent`, ruff + pyright (strict for src/voice_agent/domain),
pytest + pytest-asyncio, pre-commit, GitHub Actions CI (lint, typecheck, unit tests; evals job stubbed),
.env.example with all config keys from 03-tech-stack (no real values), config.py with pydantic-settings
and VOICE_PROFILE. Do not add Pipecat yet. Use plan mode first and show me the file list before writing.
```

## M1 — Domena + DB + seed (1.5 d)
**DoD:** schemat z [04](04-data-model.md); seed z walidatorem `--check`; reguły biznesowe z tabeli; holdy z TTL; test współbieżny (ostatni stolik → dokładnie 1 sukces); zero importów Pipecat/LLM w `domain/`.

**Prompt:**
```text
Implement M1 from docs/plan/08-roadmap.md using docs/plan/04-data-model.md as the spec.
1) db/schema.sql exactly as specified; db/seed.py loads data/seed/*.yaml via Pydantic models,
   supports --reset and --check (the three validator rules in 04-data-model).
2) domain/: Clock protocol (+ FrozenClock), availability (15-min grid, best-fit table, alternatives rule),
   holds (TTL 5 min, new hold in same conversation releases the previous one), reservations
   (BEGIN IMMEDIATE, slot rows, code alphabet without 0/O/1/I), menu fuzzy search (rapidfuzz),
   allergens (synonym map, UNKNOWN when no row, related_ingredients).
3) Typed domain errors matching the error codes in docs/plan/05-tools-spec.md.
4) Tests first for each business rule in the 04 table, plus one concurrency test for double booking.
Generate seed YAML with the prompt from 04-data-model, then make it pass --check.
domain/ must not import pipecat or any LLM client. Keep it simple: no ORM, no migrations framework.
```

## M2 — Narzędzia + agent tekstowy + guard (2 d)
**DoD:** 6 narzędzi wg [05](05-tools-spec.md); pipeline Pipecat w trybie tekstowym (`uv run voice-agent chat`); `ConversationState` + system prompt z [06](06-dialogue-guardrails.md); `AllergenClaimGuard` z ~20 testami zdań; failover LLM Groq → Gemini; scenariusz flagowy przechodzi ręcznie w CLI; wybór modelu agenta zapisany w 3–5 zdaniach w `docs/notes/model-choice.md`.

**Prompt:**
```text
Implement M2. Specs: docs/plan/05-tools-spec.md, docs/plan/06-dialogue-guardrails.md, docs/plan/02-architecture.md.
Before coding, use the pipecat-context-hub MCP to find (a) the current way to register function-call
handlers on an LLM service, (b) the simplest supported way to run a pipeline with text input/output and
no STT/TTS, (c) ServiceSwitcher with failover strategy, (d) how to write a custom FrameProcessor that
buffers LLM text until sentence end and handles interruption frames. Write short findings with doc links
to docs/notes/pipecat-api-notes.md, then implement. If (b) is impractical, use the fallback in ADR-0006.
Tools are thin adapters over domain/. Readback and spoken_answer come from dialogue/renderers.py.
create_reservation must return CONFIRMATION_REQUIRED if the hold was created in the same user turn.
Provide `uv run voice-agent chat --profile cloud`. Unit-test the guard with ~20 positive/negative sentences.
```

## M3 — Harness L1 + bramka CI (1.5 d)
**DoD:** format YAML z [07](07-evaluation.md); matchery; tryby live/replay z kasetami; metryki wg definicji; `latest.md` + `results.jsonl`; `thresholds.yaml`; **~25 scenariuszy** (flagowy + core + allergen + kilka edge/adversarial); CI uruchamia replay i blokuje merge.

**Prompt:**
```text
Implement M3 per docs/plan/07-evaluation.md (core part only; skip the simulated-user mode).
The harness drives the same text-mode pipeline from M2. Implement matchers (exact, contains, icontains,
digits, any_of), per-turn unordered / cross-turn ordered tool-call matching, DB-state assertions against
a fresh seeded SQLite per run, cassette record/replay (replay miss = failure), the metrics in the table,
markdown + jsonl reports, exit code from thresholds.yaml. Write ~25 scenarios: the flagship, core,
allergen, and the edge cases marked "text eval" in 06. Record cassettes in live mode, commit them,
wire CI to replay. Never lower a threshold to make a run pass; report failures instead.
```

## M3.5 — Naiwny baseline od zera (1 d, twardy time-box)
**Po co:** zamienia ADR-0001 z opinii w pomiar i pokazuje, że rozumiesz, co robi framework. W README zajmuje **jeden wiersz tabeli i 2 zdania** — nie więcej.

**Zakres (celowo minimalny, ~200–300 linii):**
- Przeglądarka: `getUserMedia` → AudioWorklet → PCM 16 kHz → WebSocket (jeden plik `index.html`, vanilla JS).
- Serwer: endpoint WebSocket w FastAPI; koniec wypowiedzi = Silero VAD + stała cisza 700 ms; faster-whisper; **te same** `tools/` i `dialogue/` co w M2 (pętla tool callingu bez streamingu); Kokoro syntetyzuje całą odpowiedź → WAV → przeglądarka odtwarza.
- **Bez** barge-in, bez streamingu TTS, bez echo cancellation (słuchawki wymagane).
- Logowanie czasów per tura w tym samym formacie JSONL co M4.

**DoD:** działa rozmowa flagowa; 10 tur zmierzonych; `baseline/README.md` z tabelą (voice-to-voice p50, time-to-first-audio) i listą „czego baseline nie umie” (barge-in, streaming, echo). Po M4 dopisany wiersz Pipecat do tej samej tabeli. Kod zamrożony — żadnych poprawek po pomiarze.

**Prompt:**
```text
Implement M3.5 per docs/plan/08-roadmap.md. Hard limit: ~300 lines total, one day.
baseline/naive_loop.py: FastAPI app with one WebSocket endpoint; receives 16 kHz mono PCM from the browser,
end-of-utterance = Silero VAD + 700 ms silence, transcribe with faster-whisper, run a simple non-streaming
tool-calling loop reusing voice_agent.tools and voice_agent.dialogue (same prompt, same guard on the final
text), synthesize the whole reply with Kokoro, send WAV back. baseline/static/index.html: vanilla JS,
AudioWorklet capture, playback of returned WAV. No Pipecat imports in baseline/. Log per-turn timings to
logs/baseline_turns.jsonl (same keys as the M4 observer output). Write baseline/README.md with run steps,
a results table placeholder, and the known limitations list. Do not add features beyond this.
```

## M4 — Pipeline głosowy w Pipecacie (2 d)
**DoD:** `uv run voice-agent voice` → przeglądarka (prebuilt client) → rozmowa działa; Silero VAD + Smart Turn v3; Whisper na CUDA; Kokoro; guard przed TTS; barge-in działa; latency per tura do `logs/turns.jsonl`; profile `cloud|cpu`; Docker z GPU.

**Prompt:**
```text
Implement M4. Reuse the M2 pipeline; add the voice channel with SmallWebRTCTransport served by our FastAPI
app (/api/offer) and the prebuilt browser client for development, Silero VAD, Smart Turn v3 (local),
WhisperSTTService (CUDA, model from config), KokoroTTSService, AllergenClaimGuard between LLM and TTS,
UserBotLatencyObserver writing one JSON line per turn to logs/turns.jsonl (same keys as baseline).
Add the tool-call filler from 05-tools-spec. Verify every API against the pipecat-context-hub
(check_deprecation on each import). Provide Dockerfile + docker-compose with GPU.
Give me a short manual test checklist covering E1, E2, E14 from 06.
```

## M5 — Pomiary + hardening (1.5 d)
**DoD:**
- Latency: 20 tur na profil `cloud` i `cpu` + 10 tur baseline → p50/p95 w `docs/results/latency.md`.
- STT bench (odchudzony, [07](07-evaluation.md)): 30 wypowiedzi, warunki czysto / szum 10 dB / **linia telefoniczna 8 kHz μ-law**, 2 konfiguracje STT, 10 własnych nagrań → WER + slot error rate.
- Pipecat Evals: 5 scenariuszy audio przechodzi.
- Hardening: fault injection (scenariusze `fault`), failover na mocku 429, idle handling.

**Prompt:**
```text
Implement M5 per docs/plan/07-evaluation.md (L2 section, reduced scope) and the M5 DoD in 08-roadmap.
stt_bench.py: synthesize the 30 utterances with Kokoro (2 voices), add the 10 self-recorded clips from
evals/audio/recordings/, apply three conditions (clean, 10 dB noise, telephone: resample to 8 kHz, mu-law
encode/decode, back to 16 kHz), run two STT configs, report WER and slot error rate (slots extracted by the
text-mode agent's check_availability arguments). Add 5 Pipecat Evals audio scenarios (verify the current
scenario format via pipecat-context-hub). Add fault-injection scenarios and a failover test with a mocked 429.
Write results to docs/results/*.md generated by scripts, never by hand.
```

## M6 — Frontend + demo + README (1.5 d)
**DoD:** minimalny klient: przycisk połącz/rozłącz, transkrypt na żywo, lista tool calli z czasem, badge latency ostatniej tury, znacznik gdy guard zadziałał (jedna strona, bez routingu, bez stanu globalnego); demo video 2 min; README EN wg [09](09-portfolio-presentation.md) z liczbami z raportów; diagram jako obraz; licencje.

**Prompt:**
```text
Implement M6. client/: React + Vite single page using the Pipecat JS client SDK and the SmallWebRTC
transport (check current package names and hooks in pipecat-context-hub). Show: connect button, live
transcript, tool-call list with durations, last-turn latency badge, a marker when AllergenClaimGuard
replaced a sentence (send a custom server message for it). Keep it to one page and plain CSS.
Then write README.md per docs/plan/09-portfolio-presentation.md; generate the metrics tables with
scripts/update_readme_metrics.py from evals/reports and docs/results. No hand-typed numbers.
```

---

## M7 — Opcjonalne rozszerzenia (w kolejności wartości / koszt)

| # | Rozszerzenie | Wartość | Time-box |
|---|---|---|---|
| 1 | **Fast-path router** — mały klasyfikator (embeddingi + regresja logistyczna) obsługuje proste pojedyncze intencje (godziny, adres) bez LLM; LLM przy niskiej pewności lub multi-intent. Raport: % tur ominiętych, zysk latencji/tokenów, accuracy routera. | Kaskada rules → ML → LLM, pasuje do profilu DS | 2 d |
| 2 | Porównanie z speech-to-speech (Gemini Live, jeśli dostępny na free tierze) — latencja vs brak możliwości guarda | Modny temat, mocny argument w README | 1 d |
| 3 | 🇵🇱 Polski (Whisper PL + TTS z polskim głosem; weryfikacja licencji głosu) | Lokalny rynek pracy | 1.5 d |
| 4 | Symulowany klient LLM (persony) w harnessie | Robustness | 1 d |
| 5 | LLM-guard vs regułowy guard (precision/recall) | Safety eval | 1 d |
| 6 | OTel → Jaeger, zrzut trace'u | Observability | 0.5 d |
| 7 | PostgreSQL + `tstzrange` exclusion constraint | Bazy danych | 1 d |

Nie robimy: LiveKit równolegle, Twilio/PSTN, własny serwer WebRTC, Pipecat Flows.

## Rytuał po każdym milestonie
```bash
uv run ruff check . && uv run pyright && uv run pytest -q
uv run python -m evals.run --suite all --mode replay   # od M3
```
Zaktualizuj status w tabeli; jeśli odbiegłeś od planu — krótki ADR; commit z prefiksem `M<n>:`.
