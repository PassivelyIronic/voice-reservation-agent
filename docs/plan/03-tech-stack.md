---
title: Tech stack
tags: [voice-ai, stack, free-tier]
updated: 2026-10-26
verified: 2026-10-26
---

# 03 — Tech stack

> [!NOTE]
> Stan zweryfikowany 2026-10-26. Limity free tierów i nazwy modeli zmieniają się co kwartał — przed M2 sprawdź konsolę providera. W kodzie modele są **wyłącznie w konfiguracji** (`.env` / `config.py`), nigdy hardcoded.

## Stack docelowy

| Warstwa | Wybór | Koszt | Alternatywa / fallback |
|---|---|---|---|
| Język / tooling | Python 3.12, `uv`, `ruff`, `pyright`, `pytest` + `pytest-asyncio`, `pre-commit` | 0 | — |
| Voice framework | **Pipecat 1.x** (BSD-2) | 0 | LiveKit Agents (patrz ADR-0001) |
| Transport | `SmallWebRTCTransport` (P2P WebRTC, bez serwera mediów i konta) | 0 | WebSocket (tylko eval) |
| VAD | Silero VAD | 0 | — |
| Turn detection | Smart Turn v3 (`LocalSmartTurnAnalyzerV3`, ONNX na CPU, wagi w paczce) | 0 | sam VAD z dłuższym `stop_secs` |
| STT | **faster-whisper** przez `WhisperSTTService` (CUDA, `large-v3-turbo` lub `distil-*`) | 0 | Groq `whisper-large-v3-turbo` (free tier) |
| LLM (tool calling) | **Groq free tier** (OpenAI-compatible) | 0 | Gemini Flash (free tier) → Ollama lokalnie |
| TTS | **Kokoro-82M** (`KokoroTTSService`, ONNX, lokalnie) | 0 | Piper (opcja M7: polski) |
| Failover | `ServiceSwitcher` + `ServiceSwitcherStrategyFailover` | 0 | — |
| Backend HTTP | FastAPI (signaling `/api/offer`, `/healthz`, read-only `/reservations`) | 0 | runner deweloperski Pipecata |
| DB | SQLite (stdlib `sqlite3`, surowe SQL w `schema.sql`) | 0 | PostgreSQL (opcja M7, ADR-0005) |
| Walidacja / config | Pydantic v2, `pydantic-settings` | 0 | — |
| Fuzzy matching menu | `rapidfuzz` | 0 | — |
| Logi | `loguru` (już używany przez Pipecat) → JSONL sink | 0 | — |
| Tracing | OpenTelemetry (`pipecat-ai[tracing]`) → Jaeger w docker compose | 0 | Langfuse self-host |
| Ewaluacja | własny text harness + **Pipecat Evals** (`pipecat eval`) dla audio | 0 | — |
| Frontend | dev: `pipecat-ai-small-webrtc-prebuilt`; M6: minimalny React + Vite + klient JS Pipecata | 0 | — |
| Baseline (M3.5) | FastAPI WebSocket + AudioWorklet (vanilla JS), bez Pipecata | 0 | — |
| CI | GitHub Actions (public repo) | 0 | — |
| Konteneryzacja | Docker + docker compose (NVIDIA Container Toolkit dla GPU) | 0 | — |
| Dev z AI | Claude Code + MCP **Pipecat Context Hub** | — | `docs.pipecat.ai/llms.txt` |

## Darmowe tiery — snapshot (zweryfikuj przed użyciem)

### Groq (OpenAI-compatible, brak karty wymaganej)
Limity są **per model, per organizacja** (nie per klucz). Dane z dokumentacji rate limits (stan sierpień–październik 2026):

| Model | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `llama-3.3-70b-versatile` | 30 | 1 000 | 12 K | 100 K |
| `openai/gpt-oss-120b` | 30 | 1 000 | 8 K | 200 K |
| `llama-3.1-8b-instant` | 30 | 14 400 | 6 K | 500 K |
| `whisper-large-v3-turbo` (STT) | 20 | 2 000 audio req | — | — |

**Konsekwencja projektowa:** pojedyncze wywołanie agenta to ~2–3 K tokenów wejścia (system prompt + 6 narzędzi + historia). 100 K TPD ≈ 35–50 wywołań LLM dziennie na modelu 70B. Dlatego:
- harness ewaluacyjny ma **tryb replay** (cache odpowiedzi LLM, klucz = hash(model, messages, tools)) — CI nie zużywa limitów,
- symulator klienta (user simulator) działa na `llama-3.1-8b-instant` (najwyższe limity),
- model agenta wybierany empirycznie w M2 (kandydaci: `gpt-oss-120b`, `llama-3.3-70b-versatile`, inne z tool callingiem dostępne w konsoli) — kryterium: tool-call accuracy na zestawie rdzeniowym, potem TTFT.

### Google Gemini API (AI Studio)
- Free tier obejmuje tylko modele **Flash i Flash-Lite**; modele Pro wypadły z free tieru w kwietniu 2026.
- Seria 2.5 ma zaplanowane wyłączenie — używaj aktualnej linii Flash (ID sprawdź w AI Studio).
- Na free tierze Google może używać wejść/wyjść do ulepszania modeli — akceptowalne, bo dane są fikcyjne. Nigdy nie wysyłaj tam prawdziwych danych osobowych.
- Rola: fallback #1 w `ServiceSwitcher`.

### Ollama (lokalnie)
- Rola: fallback #2 + wiersz w tabeli „local vs cloud”.
- Kandydat: model 7–8B z dobrym tool callingiem (Qwen-family, Q4_K_M). Na 8 GB VRAM współdzielonym z Whisperem → Whisper na `distil`/`small` lub CPU przy aktywnym Ollama.

## Budżet VRAM (RTX 4060 8 GB) — szacunki do potwierdzenia pomiarem

| Konfiguracja | STT | LLM | TTS | Suma |
|---|---|---|---|---|
| **A: cloud LLM (domyślna)** | whisper turbo GPU fp16/int8 ~1–2 GB | Groq (0) | Kokoro CPU (0) | ~2 GB ✅ |
| **B: full local** | whisper `small` GPU ~0.5–1 GB | Ollama 7B Q4 ~5 GB | Kokoro CPU | ~6 GB ⚠️ (KV cache!) |
| **C: zero GPU** | Groq Whisper | Groq | Kokoro CPU | 0 ✅ |

Konfiguracje wybierane profilem: `VOICE_PROFILE=cloud|cpu` (rdzeń); `local` (B) tylko opcjonalnie — na 8 GB VRAM i tak jest na granicy. Tabela porównawcza A vs C (+ baseline z M3.5) trafia do README (z pomiarów).

## Licencje (sprawdź przed publikacją — wpis w README „Third-party licenses”)

| Komponent | Licencja (wg wiedzy na 2026-10) | Status |
|---|---|---|
| Pipecat | BSD-2-Clause | ✅ |
| faster-whisper / Whisper weights | MIT | ✅ |
| Kokoro-82M | Apache-2.0 | ✅ zweryfikuj model card |
| Silero VAD | MIT | ✅ |
| Smart Turn v3 | open source (pipecat-ai/smart-turn) | ⚠️ zweryfikuj plik LICENSE |
| Piper (opcja M7) | rozwój przeniesiony do forka na GPL; głosy mają własne licencje | ⚠️ zweryfikuj przed użyciem |
| SQLite | public domain | ✅ |

> [!WARNING]
> Lekcja z poprzednich projektów: każda licencja modelu/głosu, który ląduje w demo, musi być wymieniona w README. Brak = nie publikujemy.

## Odrzucone opcje (skrót; pełne uzasadnienia w ADR)

| Opcja | Dlaczego nie (w tym projekcie) |
|---|---|
| LiveKit Agents | Dobry framework, ale wymaga serwera LiveKit (self-host docker lub Cloud); semantyczny turn detector ma licencję ograniczoną do frameworka; więcej infrastruktury niż potrzeba dla demo P2P. Rozważony w ADR-0001. |
| Deepgram Voice Agent API + Twilio | Zamknięty orkiestrator (mniej do pokazania), kredyty trial ≠ darmowe, telefonia płatna. |
| Speech-to-speech (Gemini Live, OpenAI Realtime) | Brak punktu, w którym da się zweryfikować tekst przed syntezą → guardrail alergenów niemożliwy do wyegzekwowania. Opcjonalny eksperyment porównawczy (latency) w M7. |
| LangChain / LlamaIndex | Nie ma tu RAG; tool calling obsługuje Pipecat + LLM provider. Dodatkowa warstwa bez wartości. |
| Pipecat Flows (state machine) | Rozważony; multi-intent w jednej wypowiedzi (rezerwacja + alergen) wymaga narzędzi dostępnych globalnie. Wybrano: pojedynczy agent + walidacja stanu w warstwie narzędzi (ADR-0004). |
