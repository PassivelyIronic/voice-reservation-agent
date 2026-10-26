---
title: "ADR-0002: Kaskada STT → LLM → TTS zamiast speech-to-speech"
status: accepted
date: 2026-10-26
tags: [adr]
---

# ADR-0002: Architektura kaskadowa

## Kontekst
Modele speech-to-speech (Gemini Live, OpenAI Realtime) mają niższą latencję i naturalniejszą prozodię. Wymaganie: odpowiedzi o alergenach wyłącznie z weryfikowalnego pola w bazie, bez zmyślania.

## Decyzja
Kaskada: VAD/turn → STT → LLM (tools) → **AllergenClaimGuard** → TTS.

## Uzasadnienie
1. **Guardrail wymaga tekstu przed syntezą.** W S2S model generuje audio bezpośrednio — nie ma punktu, w którym deterministycznie zweryfikujemy twierdzenie przed jego wypowiedzeniem.
2. **Obserwowalność:** osobne TTFB per etap → konkretna optymalizacja zamiast „czarnej skrzynki”.
3. **Wymienność:** każdy etap ma lokalny i chmurowy wariant (profile cloud/cpu, opcjonalnie local).
4. **Koszt:** darmowe lokalne STT/TTS; S2S na free tierze ma niskie limity i nie działa offline.

## Konsekwencje
- (−) Wyższa latencja niż S2S → mitigacje: Smart Turn, streaming TTS od pierwszego zdania, filler przy tool callu, szybki provider LLM.
- (−) Utrata prozodii wejścia (ton, emocje) — nieistotne dla rezerwacji.
- Opcja M7: zmierzyć S2S na tym samym scenariuszu i opublikować porównanie latencji vs brak guarda.
