---
title: "ADR-0001: Pipecat zamiast LiveKit Agents"
status: accepted
date: 2026-10-26
tags: [adr]
---

# ADR-0001: Pipecat + SmallWebRTC zamiast LiveKit Agents

## Kontekst
Potrzebny open-source framework real-time voice w Pythonie, uruchamialny za 0 zł na laptopie (RTX 4060 8 GB), z lokalnym STT/TTS, tool callingiem i możliwością wpięcia własnego procesora między LLM a TTS (guard alergenów).

## Rozważane opcje
| Kryterium | Pipecat 1.x | LiveKit Agents 1.x |
|---|---|---|
| Licencja | BSD-2 | Apache-2.0 (semantyczny turn detector: licencja modelu ograniczona do użycia z frameworkiem) |
| Infrastruktura dla demo | brak — `SmallWebRTCTransport` P2P | serwer LiveKit (docker self-host) lub LiveKit Cloud |
| Lokalny STT/TTS | wbudowane: `WhisperSTTService` (faster-whisper), `KokoroTTSService` (ONNX) | przez pluginy/OpenAI-compatible endpointy |
| Turn detection lokalnie | Smart Turn v3, ONNX CPU, wagi w paczce | v1-mini lokalnie przy self-host |
| Własny procesor w środku pipeline | natywnie (pipeline ramek) | możliwe przez hooki, mniej bezpośrednio |
| Ewaluacja | Pipecat Evals (scenariusze YAML, lokalny TTS/STT/judge, exit code) | własna |
| Wsparcie dla coding agentów | Pipecat Context Hub (MCP) | MCP docs server |
| Skala / telefonia | dobra | lepsza (SFU, SIP) |

## Decyzja
Pipecat. Jawny pipeline ramek pozwala pokazać i zmierzyć każdy etap oraz wpiąć `AllergenClaimGuard` jako zwykły procesor. P2P transport eliminuje infrastrukturę.

## Weryfikacja decyzji
M3.5: naiwna pętla od zera (FastAPI WebSocket + AudioWorklet, ~300 linii, bez frameworka) na tych samych narzędziach i modelach. Pomiar latencji i lista brakujących funkcji (barge-in, streaming TTS, echo) obok Pipecata w README — decyzja oparta na pomiarze, nie na opinii.

Odrzucone dodatkowo: własny pełny transport/orkiestracja jako produkt (tygodnie pracy nad rozwiązanymi problemami, gorsza jakość) oraz LiveKit równolegle (dublowanie pracy).

## Konsekwencje
- (+) Zero infrastruktury, wszystko lokalnie; ewaluacja audio bez kosztów.
- (+) Bezpośrednia kontrola nad kolejnością procesorów.
- (−) `SmallWebRTCTransport` nie jest przeznaczony do dużej skali — akceptowalne (demo, 1 sesja). Opisane w Limitations.
- (−) Szybko ewoluujące API (seria 1.x, częste wydania) → obowiązek weryfikacji importów przez Context Hub (`check_deprecation`).
- Rewizja, jeśli: potrzebna telefonia SIP lub > kilka równoległych sesji.
