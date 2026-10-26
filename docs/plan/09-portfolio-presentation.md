---
title: Prezentacja w portfolio
tags: [voice-ai, portfolio, readme]
updated: 2026-10-26
---

# 09 — Prezentacja w portfolio

Rekruter poświęca repo ~60–90 sekund. W tym czasie musi zobaczyć: **co to robi (wideo), jak jest zbudowane (diagram), skąd wiadomo, że działa (liczby), jakie decyzje podjęto (trade-offs).**

README ma być krótkie: pierwszy ekran = opis + wideo + diagram + tabela wyników. Szczegóły (pełna macierz edge cases, ADR-y, specyfikacja narzędzi) tylko jako linki do `docs/` — dla tych nielicznych, którzy zajrzą głębiej. Cel: README czytelne w 2 minuty.

## Szkielet README (EN)

```markdown
# Osteria Verde — Real-time Voice Reservation Agent

> Voice agent that books tables and answers allergen questions in real time —
> with a deterministic allergen guardrail and a CI-gated evaluation suite. 100% free/open stack.

[▶ 2-min demo video]  ·  [Architecture]  ·  [Results]  ·  [Design decisions]

## Demo
GIF (10 s, multi-intent turn) + link do pełnego wideo.

## Architecture
Diagram (PNG z Mermaid) + 5 zdań: cascade STT → LLM(tools) → guard → TTS; why cascade over speech-to-speech.

## Results  (auto-generated from evals/reports — commit abc123, 2026-xx-xx)
| Metric | Value | Gate |
| Task completion (core, n=…) | …% | ≥90% |
| Tool-call F1 | … | ≥0.90 |
| Allergen hallucinations (spoken) | 0 | =0 |
| Allergen claims intercepted by guard | …% | — |
| Handoff precision / recall | … / … | — |
| Voice-to-voice latency p50 / p95 (RTX 4060 + Groq) | … / … s | — |
| LLM calls / conversation | … | — |

### Latency: from-scratch baseline vs Pipecat
| Variant | p50 | p95 | Barge-in | Streaming TTS |
| Naive WebSocket loop (baseline/, ~300 LOC) | … | … | ✗ | ✗ |
| Pipecat, profile cloud | … | … | ✓ | ✓ |
| Pipecat, profile cpu | … | … | ✓ | ✓ |

2 zdania: why a framework after measuring the naive version.

### STT robustness (slot error rate)
| Condition | local Whisper | Groq Whisper |
| clean | … | … |
| 10 dB noise | … | … |
| telephone (8 kHz μ-law) | … | … |

## Does every part need an LLM?
Tabela z docs/06 (skrócona) — the headline engineering-judgment section.

## Safety: allergen guardrail
3 zdania + przykład zdania zablokowanego (z logów).

## Failure handling
5 najważniejszych wierszy z macierzy E1–E18 + link do pełnej tabeli w docs.

## Tool definitions
Link do wygenerowanego `docs/tools.md` (z Pydantic).

## Sample conversation
Transkrypt flagowego scenariusza z adnotacjami tool calli i latency.

## Run it
docker compose up (GPU) / uv run voice-agent voice --profile cpu

## Limitations (honest)
- English only; TTS-synthesized eval audio is easier than real callers (mitigated by 10 self-recorded clips).
- Free-tier rate limits; single concurrent session tested.
- Fictional data; allergen records are illustrative, not real food-safety guidance.

## Third-party licenses
```

## Demo video — scenariusz (2–3 min)

1. **0:00–0:15** — kadr: przeglądarka z panelem debug; jedno zdanie, co pokazujemy.
2. **0:15–1:00** — scenariusz flagowy (rezerwacja + pesto). Panel pokazuje równoległe tool calle i latency.
3. **1:00–1:25** — barge-in: przerwanie readbacku i korekta godziny.
4. **1:25–1:50** — danie bez rekordu alergenu → odmowa + oferta handoffu; w panelu `guard` (jeśli zadziałał).
5. **1:50–2:10** — brak miejsc w piątek → alternatywy.
6. **2:10–2:30** — terminal: `evals.run` → zielona tabela metryk.

Nagrywaj OBS-em, audio z mikrofonu + systemu. Bez muzyki.

## Checklista „no unverified claims”

- [ ] Każda liczba w README pochodzi z pliku raportu z datą i commitem.
- [ ] Opisane zachowania mają test (link do scenariusza lub testu).
- [ ] Domyślny tryb uruchomienia to prawdziwe modele — żadnego ukrytego mock mode; tryb mock/replay jest jawnie opisany.
- [ ] Licencje wszystkich modeli/głosów wymienione.
- [ ] Sekcja Limitations jest konkretna.
- [ ] `.env.example` kompletny, żadnych sekretów w historii gita.

## Jak opisać projekt w CV (1 linia + 2 bullety)

> **Real-time Voice Reservation Agent** — Pipecat, WebRTC, faster-whisper, Kokoro, Groq, SQLite
> - Built a cascaded voice agent with tool calling and a deterministic allergen guardrail; CI gate enforces zero unverified allergen claims across N evaluation scenarios.
> - Measured voice-to-voice latency (p50 X s) against a from-scratch WebSocket baseline and across local/cloud model profiles on an 8 GB GPU.

(X i N wpisz dopiero po pomiarze.)
