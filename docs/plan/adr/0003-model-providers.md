---
title: "ADR-0003: Dobór providerów modeli (darmowy stack)"
status: accepted
date: 2026-10-26
tags: [adr]
---

# ADR-0003: Providerzy modeli

## Kontekst
Budżet 0 zł. Sprzęt: RTX 4060 8 GB, 16 GB RAM. LLM musi niezawodnie wywoływać narzędzia (równolegle), z niskim TTFT.

## Decyzja
| Rola | Domyślnie | Fallback | Uzasadnienie |
|---|---|---|---|
| STT | faster-whisper lokalnie (CUDA) | Groq Whisper (free tier) | lokalnie = 0 limitów, prywatność; ~1–2 GB VRAM |
| LLM | Groq free tier | Gemini Flash free tier → Ollama lokalnie | lokalny 7–8B na 8 GB jest słabszy w tool callingu i konkuruje o VRAM ze STT |
| TTS | Kokoro-82M lokalnie (ONNX, CPU) | — | jakość EN, Apache-2.0, brak kosztu |
| User simulator (eval) | Groq `llama-3.1-8b-instant` | Ollama | najwyższe dzienne limity |
| LLM-as-judge (eval) | inny model niż agent (Gemini Flash lub Ollama) | — | unikanie self-preference |

Konkretny model agenta wybierany **pomiarem w M2** (tool-call accuracy na zestawie rdzeniowym, potem TTFT), nie z góry.

## Konsekwencje
- (−) Limity TPD free tieru (rząd 100–200 K tokenów/dzień na duży model) → obowiązkowy tryb replay w ewaluacji, przycinanie kontekstu, `ConversationState` zamiast pełnej historii.
- (−) Free tier Gemini może wykorzystywać dane do ulepszania modeli → tylko dane fikcyjne (już założone).
- (+) Tabela „local vs cloud” jako naturalny produkt projektu.
- Wszystkie identyfikatory modeli wyłącznie w konfiguracji.
