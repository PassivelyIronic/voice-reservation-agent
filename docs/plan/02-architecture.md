---
title: Architektura
tags: [voice-ai, architecture]
updated: 2026-10-26
---

# 02 — Architektura

## Widok systemu

```mermaid
flowchart LR
    subgraph Client["Przeglądarka"]
        MIC[Mikrofon] --> WRTC_C[WebRTC client<br/>prebuilt / React]
        WRTC_C --> SPK[Głośnik]
        WRTC_C -.RTVI events.-> UI[Debug panel:<br/>transkrypt, tool calls, latency]
    end

    subgraph Server["Python process (bot)"]
        direction LR
        IN[SmallWebRTC<br/>input] --> VAD[Silero VAD<br/>+ Smart Turn v3]
        VAD --> STT[STT<br/>faster-whisper]
        STT --> UAGG[User context<br/>aggregator]
        UAGG --> LLM[LLM service<br/>Groq / Gemini / Ollama<br/>ServiceSwitcher failover]
        LLM -->|function call| TOOLS[Tool handlers]
        TOOLS --> DOMAIN[Domain services<br/>availability · reservations · menu · allergens]
        DOMAIN --> DB[(SQLite)]
        TOOLS -->|result JSON| LLM
        LLM --> GUARD[AllergenClaimGuard<br/>FrameProcessor]
        GUARD --> TTS[TTS<br/>Kokoro ONNX]
        TTS --> OUT[SmallWebRTC<br/>output]
        OUT --> AAGG[Assistant context<br/>aggregator]
    end

    WRTC_C <==>|audio P2P| IN
    OUT ==> WRTC_C
    Server -.OTel spans.-> JAEGER[(Jaeger<br/>opcjonalnie)]
    Server -.JSONL.-> LOGS[(logs/turns.jsonl)]
```

## Warstwy (dependency rule: strzałki tylko w dół)

```
channels/      voice_webrtc.py, text_cli.py           ← wejście/wyjście
pipeline/      bot.py, processors/, observers/        ← Pipecat: składanie pipeline
dialogue/      prompts, state, renderers (templates)  ← polityka rozmowy
tools/         schemas, handlers, registry            ← adapter LLM ↔ domena
domain/        availability, reservations, menu, allergens, clock  ← czysty Python, zero I/O frameworków
db/            schema.sql, repository, seed            ← SQLite
```

**Reguła:** `domain/` nie importuje Pipecata ani klienta LLM. Dzięki temu 80% logiki testuje się bez modeli, a ten sam kod obsługuje kanał głosowy, tekstowy i eval.

## Przepływ jednej tury (multi-intent)

```mermaid
sequenceDiagram
    autonumber
    participant U as Klient (audio)
    participant P as Pipeline (VAD/STT)
    participant L as LLM
    participant T as Tools/Domain
    participant G as AllergenGuard
    participant S as TTS

    U->>P: "table for 4 at 7:30 tomorrow, does pesto have nuts?"
    P->>L: transkrypt + kontekst (today=2026-10-26, Europe/Warsaw)
    par równoległe tool calls
        L->>T: check_availability(2026-10-27, 19:30, 4)
        T-->>L: {available:true, hold_id:"H-91", slot:"19:30", table:"T7"}
    and
        L->>T: search_menu("pesto") → get_allergen_info(item_id, ["nuts"])
        T-->>L: {status:"FREE", note_ingredients:["pine nuts"], spoken_answer:"…"}
    end
    L->>G: tekst odpowiedzi (stream)
    G->>G: porównaj twierdzenia o alergenach z ostatnim tool result
    G->>S: tekst (bez zmian / zastąpiony bezpiecznym szablonem)
    S->>U: audio
    U->>P: "yes, name is Anna, 555 0101"
    P->>L: transkrypt
    L->>T: create_reservation(hold_id:"H-91", name, phone)
    T-->>L: {reservation_id, code:"OV-4F2K", readback}
    L->>S: potwierdzenie (readback z szablonu)
```

## Kluczowe mechanizmy

### 1. Hold → confirm → commit (two-phase booking)
`check_availability` nie tylko odpowiada „jest/nie ma”, ale zakłada **hold** (soft-lock na 5 min) i zwraca `hold_id`. `create_reservation` przyjmuje wyłącznie `hold_id` — LLM fizycznie nie może zarezerwować terminu, którego nie sprawdził, ani „wymyślić” godziny. Hold wygasa → slot wraca do puli.

### 2. Readback renderowany deterministycznie
Daty, godziny, liczba osób i kod potwierdzenia wypowiadane klientowi pochodzą z pola `readback` w wyniku narzędzia (szablon w `dialogue/renderers.py`), nie z parafrazy LLM. Eliminuje klasę błędów „7:30 PM” vs „7:30 AM”.

### 3. AllergenClaimGuard (procesor między LLM a TTS)
Szczegóły w [06 — Dialog i guardrails](06-dialogue-guardrails.md). Zasada: każde zdanie zawierające twierdzenie o alergenie musi mieć pokrycie w wyniku `get_allergen_info` z bieżącej tury; inaczej zdanie jest zastępowane bezpiecznym szablonem + oferta handoffu. Możliwe tylko w architekturze kaskadowej ([ADR-0002](adr/0002-cascaded-pipeline.md)).

### 4. Failover providerów
LLM opakowany w `ServiceSwitcher` ze strategią failover (Groq → Gemini Flash → Ollama). Błędy permanentne (zły klucz) vs przejściowe (429/503) rozróżnia Pipecat (`is_usable`, `ErrorCategory`). Przełączenie logowane jako zdarzenie i liczone w raporcie.

### 5. Context management
- System prompt + definicje narzędzi stałe (prompt caching po stronie providera, jeśli dostępny).
- Historia przycinana do ostatnich N tur + strukturalny `ConversationState` (party_size, date, time, hold_id, name) wstrzykiwany jako krótki blok zamiast pełnej historii — ogranicza tokeny (limity TPD free tieru).

## Latency budget (cel, do zmierzenia)

| Etap | Budżet p50 | Uwagi |
|---|---|---|
| End-of-turn (VAD stop + Smart Turn) | 200–400 ms | VAD `stop_secs≈0.2` + Smart Turn < 100 ms na CPU |
| STT (faster-whisper, segmentowy, GPU) | 150–350 ms | segment po końcu tury, nie streaming |
| LLM TTFT (Groq) | 200–500 ms | zależy od modelu i obciążenia free tieru |
| Tool execution (SQLite) | < 20 ms | lokalnie |
| Drugi LLM call po tool result | 200–500 ms | dlatego równoległe tool calls mają znaczenie |
| TTS TTFB (Kokoro) | 100–300 ms | zdania streamowane od pierwszego |
| **Voice-to-voice** | **≤ 1.5 s p50** | mierzone przez `UserBotLatencyObserver` |

Mitigacje gdy budżet przekroczony: filler („Let me check that for you…”) wypowiadany natychmiast przy tool callu, krótszy system prompt, mniejszy model STT (`distil-*`), model LLM o niższym TTFT.

## Kanały

| Kanał | Transport | Użycie |
|---|---|---|
| `voice` | `SmallWebRTCTransport` + prebuilt UI / klient React | demo, testy manualne |
| `text` | pipeline bez STT/TTS (wejście: tekst jako ramki transkrypcji) | CLI, harness ewaluacyjny, CI |
| `eval-audio` | transport ewaluacyjny Pipecat Evals (`-t eval`) | testy audio end-to-end |

> [!IMPORTANT]
> Spike w M2: potwierdzić w Pipecat Context Hub najprostszy sposób uruchomienia tego samego pipeline'u w trybie tekstowym (np. wstrzykiwanie `TranscriptionFrame`, narzędzia testowe frameworka). Jeśli to niepraktyczne — fallback opisany w [ADR-0006](adr/0006-two-level-evaluation.md).
