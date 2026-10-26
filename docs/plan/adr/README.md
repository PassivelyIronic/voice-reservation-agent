---
title: Architecture Decision Records
tags: [adr, index]
---

# ADR — indeks

| ADR | Decyzja | Status |
|---|---|---|
| [0001](0001-pipecat-over-livekit.md) | Pipecat + SmallWebRTC zamiast LiveKit Agents | accepted |
| [0002](0002-cascaded-pipeline.md) | Kaskada STT → LLM → guard → TTS zamiast speech-to-speech | accepted |
| [0003](0003-model-providers.md) | Providerzy: faster-whisper, Groq (+Gemini/Ollama), Kokoro | accepted |
| [0004](0004-deterministic-core.md) | Deterministyczny rdzeń, LLM tylko do języka | accepted |
| [0005](0005-sqlite-slot-model.md) | SQLite + siatka slotów z `UNIQUE` | accepted |
| [0006](0006-two-level-evaluation.md) | Ewaluacja text (L1) + audio (L2) | accepted |

## Szablon nowego ADR

```markdown
---
title: "ADR-NNNN: <decyzja>"
status: proposed | accepted | superseded by ADR-XXXX
date: YYYY-MM-DD
tags: [adr]
---
# ADR-NNNN: <decyzja>
## Kontekst
## Rozważane opcje
## Decyzja
## Konsekwencje
```

Nowy ADR jest wymagany przy: zmianie providera domyślnego, obniżeniu progu ewaluacji, zmianie schematu bazy, odejściu od architektury kaskadowej.
