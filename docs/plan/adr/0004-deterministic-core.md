---
title: "ADR-0004: Deterministyczny rdzeń, LLM tylko do języka"
status: accepted
date: 2026-10-26
tags: [adr]
---

# ADR-0004: Deterministyczny rdzeń biznesowy

## Kontekst
Błędy LLM w rezerwacjach (zła godzina, nieistniejący slot) i alergenach (zmyślone „bez orzechów”) są niedopuszczalne. Rozważono: (a) agent z narzędziami i regułami w prompcie, (b) Pipecat Flows — maszyna stanów z węzłami, (c) agent z narzędziami + egzekwowanie stanu po stronie serwera.

## Decyzja
(c): pojedynczy agent z globalnie dostępnymi narzędziami; wszystkie niezmienniki egzekwowane w `domain/` i bazie:
- hold → readback → potwierdzenie w **kolejnej turze** → commit (`CONFIRMATION_REQUIRED`),
- readback/`spoken_answer` z szablonów,
- `UNKNOWN` przy braku rekordu alergenu,
- guard regułowy przed TTS.

## Dlaczego nie Pipecat Flows
Multi-intent w jednej wypowiedzi („book for 4 … and does the pesto have nuts?”) wymaga, by narzędzia menu/alergenów były dostępne w każdym stanie rezerwacji. Flows wymusza jawne przejścia i powielanie funkcji między węzłami; zysk (determinizm przebiegu) jest już zapewniony przez preconditions narzędzi. Flows pozostaje opcją, jeśli scenariusze ewaluacji pokażą chaotyczne prowadzenie rozmowy.

## Konsekwencje
- (+) Odpowiedź na „czy każda część wymaga LLM?” jest wbudowana w architekturę.
- (+) `domain/` testowalne bez modeli (szybkie, darmowe testy).
- (−) Więcej kodu niż „wszystko w prompcie” — świadomy koszt.
