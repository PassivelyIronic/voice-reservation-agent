---
title: Brief projektu
tags: [voice-ai, brief]
updated: 2026-10-26
---

# 01 — Brief

## Problem

Telefon restauracji obsługuje powtarzalne zapytania (rezerwacje, godziny, alergeny) w godzinach szczytu. Agent głosowy ma przejąć te rozmowy **bez ryzyka**: nie może podwójnie zarezerwować stolika ani zmyślić informacji o alergenie.

## Cel portfolio

Pokazać kompetencje, których rekruter AI/ML/MLOps nie zobaczy w typowym „chat z PDF”:

1. **Real-time systems** — streaming audio, VAD, turn detection, barge-in, latency per stage.
2. **Tool calling z kontraktami** — LLM wywołuje deterministyczne narzędzia; stan biznesowy jest walidowany po stronie serwera.
3. **Safety engineering** — guardrail alergenów jako procesor w pipeline (między LLM a TTS), z twardą bramką w CI.
4. **Evaluation discipline** — metryki liczone na stanie bazy, nie „na oko”; regresje blokują merge.
5. **Engineering judgment** — jawna odpowiedź na pytanie „czy każda część wymaga LLM?” (nie wymaga) + tabela local vs cloud.

## Główny scenariusz (happy path, multi-intent)

> **Klient:** „Hi, can I book a table for four at 7:30 tomorrow? Also — does your pesto have nuts? I'm allergic.”
>
> **Agent:** sprawdza dostępność (`check_availability`) **i** alergeny (`get_allergen_info`) → odpowiada na oba wątki, odczytuje rezerwację do potwierdzenia → po „yes” tworzy rezerwację (`create_reservation`) → podaje kod potwierdzenia.

Pułapka celowo wbudowana w dane: pesto zawiera **pinoli (pine nuts)**, które nie należą do 14 alergenów regulowanych w UE (kategoria „nuts” w Rozporządzeniu 1169/2011 to orzechy drzewne: migdały, laskowe, włoskie, nerkowce, pekan, brazylijskie, pistacje, makadamia). Poprawna odpowiedź to fakt z bazy + rekomendacja kontaktu z personelem przy ciężkiej alergii — nie „tak/nie” wymyślone przez LLM.

## Zakres (MVP)

- Język rozmowy: **angielski** (najlepsza jakość darmowego TTS; międzynarodowi rekruterzy). Polski = opcja (M7).
- Kanał: przeglądarka (WebRTC P2P) + tryb tekstowy (CLI, eval).
- Intencje: rezerwacja nowa, pytanie o menu, pytanie o alergen, godziny/adres, przekazanie do człowieka.
- Dane: w pełni fikcyjne, wygenerowane i zweryfikowane ręcznie.

## Non-goals (MVP)

- Telefonia PSTN (Twilio/SIP) — płatne; opcjonalnie po MVP.
- Modyfikacja/anulowanie rezerwacji.

> [!NOTE]
> Projekt jest jednym z kilku w portfolio — zakres podzielony na **rdzeń (~11 dni)** i **opcje**. Zasada i time-boxy: [Roadmapa](08-roadmap.md#zasada-anty-overkill).
- Płatności, konta użytkowników, panel admina.
- Fine-tuning modeli.
- Produkcyjny deployment publiczny (demo = nagranie wideo + `docker compose up` lokalnie).

## Kryteria sukcesu (mierzalne, docelowe — raportowane w README tylko po zmierzeniu)

| Metryka | Cel | Typ |
|---|---|---|
| Allergen hallucination count (text eval) | **0** | twarda bramka CI |
| Task completion rate (text eval, scenariusze rdzeniowe) | ≥ 90% | bramka CI |
| Tool-call accuracy (wybór + argumenty) | ≥ 90% | bramka CI |
| Handoff precision / recall | ≥ 0.9 / ≥ 0.9 | raport |
| Voice-to-voice latency p50 / p95 (lokalnie, RTX 4060 + Groq) | ≤ 1.5 s / ≤ 2.5 s | raport, nie bramka |
| Double booking pod współbieżnością | 0 | test jednostkowy |

> [!WARNING]
> Progi w tabeli to cele projektowe. README końcowe podaje **wyłącznie** wartości zmierzone przez harness (z datą, commitem, konfiguracją). Obniżanie progów wymaga osobnego ADR.
