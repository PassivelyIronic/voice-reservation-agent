---
title: "ADR-0005: SQLite i model slotowy"
status: accepted
date: 2026-10-26
tags: [adr]
---

# ADR-0005: SQLite + siatka slotów 15-min

## Kontekst
Potrzebna gwarancja braku double bookingu na poziomie bazy, przy zerowej infrastrukturze i łatwym resecie bazy dla każdego przebiegu ewaluacji.

## Decyzja
SQLite (plik; w ewaluacji świeża kopia per run). Rezerwacja zajmuje N wierszy `reservation_slots` z `UNIQUE(table_id, slot_start)`; holdy zajmują te same wiersze z `hold_id`. Insert w transakcji `BEGIN IMMEDIATE`.

## Alternatywy
- PostgreSQL + `tstzrange` + exclusion constraint (`EXCLUDE USING gist`) — elegantsze, ale wymaga serwera; przewidziane jako opcja M7.
- Sprawdzanie nakładania w aplikacji bez ograniczenia w bazie — odrzucone (wyścigi).

## Konsekwencje
- (+) Ta sama gwarancja w obu bazach; test współbieżny trywialny.
- (−) Ziarnistość 15 min (zgodna z praktyką restauracyjną).
- (−) SQLite = jeden writer; przy jednej sesji demo bez znaczenia.
