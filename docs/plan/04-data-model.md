---
title: Model danych
tags: [voice-ai, data, sql]
updated: 2026-10-26
---

# 04 — Model danych

## Zasady

1. **Dane fikcyjne.** Restauracja „Osteria Verde”, Kraków (fikcyjna), strefa czasowa `Europe/Warsaw`.
2. **Źródło prawdy = YAML w repo** (`data/seed/*.yaml`), walidowany Pydantic → ładowany do SQLite. Zmiany danych przechodzą przez code review jak kod.
3. **Brak rekordu alergenu = `UNKNOWN`.** Nigdy nie domyślamy „FREE”.
4. **Czas wstrzykiwany** (`Clock` w `domain/clock.py`) — scenariusze ewaluacyjne zamrażają „teraz”, więc wyniki są reprodukowalne.

## Schemat (SQLite)

```sql
-- Reguły restauracji
CREATE TABLE opening_hours (
  weekday       INTEGER PRIMARY KEY CHECK (weekday BETWEEN 0 AND 6), -- 0 = Monday
  open_time     TEXT,            -- 'HH:MM', NULL = zamknięte
  last_seating  TEXT,            -- ostatnia godzina rozpoczęcia rezerwacji
  close_time    TEXT
);
CREATE TABLE special_closures (
  date   TEXT PRIMARY KEY,       -- 'YYYY-MM-DD'
  reason TEXT NOT NULL
);
CREATE TABLE restaurant_info (   -- adres, parking, polityki (FAQ deterministyczne)
  topic TEXT PRIMARY KEY,        -- 'address' | 'parking' | 'dress_code' | 'large_groups' | ...
  answer TEXT NOT NULL
);

-- Stoliki i rezerwacje
CREATE TABLE dining_tables (
  id        TEXT PRIMARY KEY,    -- 'T1'..'T12'
  capacity  INTEGER NOT NULL CHECK (capacity > 0),
  zone      TEXT NOT NULL        -- 'main' | 'window' | 'terrace'
);
CREATE TABLE holds (
  id              TEXT PRIMARY KEY,        -- 'H-xxxx'
  table_id        TEXT NOT NULL REFERENCES dining_tables(id),
  date            TEXT NOT NULL,
  start_time      TEXT NOT NULL,
  party_size      INTEGER NOT NULL,
  conversation_id TEXT NOT NULL,
  expires_at      TEXT NOT NULL,           -- ISO8601 z offsetem
  status          TEXT NOT NULL CHECK (status IN ('ACTIVE','CONVERTED','EXPIRED','RELEASED'))
);
CREATE TABLE reservations (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  code           TEXT NOT NULL UNIQUE,     -- 'OV-4F2K' (bez 0/O/1/I — czytelne głosowo)
  customer_name  TEXT NOT NULL,
  phone          TEXT NOT NULL,
  party_size     INTEGER NOT NULL CHECK (party_size BETWEEN 1 AND 8),
  date           TEXT NOT NULL,
  start_time     TEXT NOT NULL,
  duration_min   INTEGER NOT NULL DEFAULT 120,
  table_id       TEXT NOT NULL REFERENCES dining_tables(id),
  notes          TEXT,                     -- np. 'nut allergy' (tylko to, co klient powiedział)
  status         TEXT NOT NULL CHECK (status IN ('CONFIRMED','CANCELLED')),
  source         TEXT NOT NULL,            -- 'voice' | 'text' | 'seed' | 'eval'
  created_at     TEXT NOT NULL
);
-- Siatka 15-min. Rezerwacja 120 min = 8 wierszy. UNIQUE = gwarancja braku double bookingu.
CREATE TABLE reservation_slots (
  table_id        TEXT NOT NULL REFERENCES dining_tables(id),
  slot_start      TEXT NOT NULL,           -- 'YYYY-MM-DDTHH:MM'
  reservation_id  INTEGER REFERENCES reservations(id),
  hold_id         TEXT REFERENCES holds(id),
  CHECK ((reservation_id IS NULL) <> (hold_id IS NULL)),
  UNIQUE (table_id, slot_start)
);

-- Menu i alergeny
CREATE TABLE allergens (                   -- 14 alergenów UE (Rozp. 1169/2011, Załącznik II)
  code    TEXT PRIMARY KEY,                -- 'gluten','crustaceans','eggs','fish','peanuts','soy','milk',
                                           -- 'nuts','celery','mustard','sesame','sulphites','lupin','molluscs'
  name_en TEXT NOT NULL,
  name_pl TEXT NOT NULL
);
CREATE TABLE menu_items (
  id           TEXT PRIMARY KEY,           -- 'pasta-pesto-genovese'
  name         TEXT NOT NULL,
  category     TEXT NOT NULL,              -- 'starter'|'pasta'|'main'|'dessert'|'drink'
  description  TEXT NOT NULL,
  price_pln    INTEGER NOT NULL,           -- grosze
  is_available INTEGER NOT NULL DEFAULT 1,
  aliases      TEXT NOT NULL DEFAULT '[]'  -- JSON: ["pesto","pesto pasta","green pasta"]
);
CREATE TABLE ingredients (
  id    TEXT PRIMARY KEY,                  -- 'pine-nuts'
  name  TEXT NOT NULL,
  related_allergen_code TEXT REFERENCES allergens(code), -- np. pine nuts → 'nuts' (mylony, NIE regulowany)
  related_note TEXT                                      -- tekst dla klienta, zatwierdzony
);
CREATE TABLE menu_item_ingredients (
  item_id       TEXT NOT NULL REFERENCES menu_items(id),
  ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
  PRIMARY KEY (item_id, ingredient_id)
);
-- ⚠️ Jedyne źródło odpowiedzi o alergenach. Brak wiersza = UNKNOWN.
CREATE TABLE menu_item_allergens (
  item_id       TEXT NOT NULL REFERENCES menu_items(id),
  allergen_code TEXT NOT NULL REFERENCES allergens(code),
  status        TEXT NOT NULL CHECK (status IN ('CONTAINS','MAY_CONTAIN','FREE')),
  verified_by   TEXT NOT NULL,             -- 'head-chef' (fikcyjne)
  verified_at   TEXT NOT NULL,
  PRIMARY KEY (item_id, allergen_code)
);

-- Operacje
CREATE TABLE handoff_tickets (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL,
  reason          TEXT NOT NULL CHECK (reason IN
                   ('large_party','allergen_unknown','severe_allergy','tool_failure',
                    'customer_request','complaint','out_of_scope')),
  summary         TEXT NOT NULL,
  created_at      TEXT NOT NULL
);
```

### Dlaczego slot table zamiast `tstzrange`
SQLite nie ma exclusion constraints. Siatka 15-min + `UNIQUE(table_id, slot_start)` daje tę samą gwarancję na poziomie bazy, działa identycznie w PostgreSQL i jest trywialna do przetestowania współbieżnie. Insert wszystkich slotów w jednej transakcji `BEGIN IMMEDIATE`; `IntegrityError` = przegrany wyścig → narzędzie zwraca alternatywy. Szczegóły: [ADR-0005](adr/0005-sqlite-slot-model.md).

## Reguły biznesowe (domain/, testowane jednostkowo)

| Reguła | Wartość | Zachowanie przy naruszeniu |
|---|---|---|
| Okno rezerwacji | dziś … +30 dni | `OUT_OF_WINDOW` + komunikat |
| Minimalne wyprzedzenie | 60 min | `TOO_SOON` |
| Godziny | wg `opening_hours`, start ≤ `last_seating` | `CLOSED` + najbliższe otwarte godziny |
| Party size | 1–8 | >8 → `LARGE_PARTY` → handoff |
| Przydział stolika | best-fit: najmniejszy stolik z `capacity ≥ party_size` | brak → alternatywy |
| Alternatywy | do 3 najbliższych slotów w ±90 min tego dnia, potem ten sam czas następnego dnia | — |
| Hold TTL | 5 min | wygasły hold → `HOLD_EXPIRED`, ponowne sprawdzenie |
| Duration | 120 min | — |
| Kod rezerwacji | `OV-` + 4 znaki z alfabetu bez `0 O 1 I` | — |

## Seed data — wymagany rozkład (testowalny)

Seed musi zawierać celowe przypadki brzegowe, bo na nich stoją scenariusze ewaluacji:

**Menu (~25 pozycji)**, w tym:
- `pasta-pesto-genovese` — pinoli (pine nuts) + parmezan; `nuts: FREE` (zweryfikowane), `milk: CONTAINS`; składnik `pine-nuts` z `related_allergen_code='nuts'` i zatwierdzoną notatką. **Pułapka główna.**
- deser z `nuts: MAY_CONTAIN` (cross-contamination, np. tiramisu przygotowywane obok cantucci).
- danie sezonowe `special-of-the-week` **bez rekordów alergenów** → `UNKNOWN` dla wszystkiego.
- danie z orzeszkami ziemnymi (`peanuts: CONTAINS`) — test, że peanuts ≠ nuts.
- danie `is_available = 0` (wyprzedane).
- 2 pozycje o podobnych nazwach (np. „Pesto Genovese” vs „Pesto Rosso”) → test dopytania.

**Stoliki:** 12 (2×2, 6×4, 3×6, 1×8).

**Godziny:** pon zamknięte; wt–czw 12:00–22:00 (last seating 21:00); pt–sob 12:00–23:00 (last seating 21:30); nd 12:00–21:00. Jedno `special_closure` w najbliższych 30 dniach.

**Istniejące rezerwacje:** generator deterministyczny (`random.Random(42)`) względem zamrożonej daty scenariusza; **piątek 19:00–20:30 w pełni zajęty** dla party ≥ 4 (scenariusz „brak miejsc”).

## Prompt do wygenerowania menu (użyj w Claude/ChatGPT, potem ręczna weryfikacja)

```text
Generate a YAML menu for a fictional Italian restaurant "Osteria Verde" with exactly 25 items
across categories: starter (5), pasta (7), main (6), dessert (5), drink (2).

For each item output:
  id (kebab-case), name, category, description (max 20 words), price_pln (integer, PLN),
  aliases (2-4 ways a caller might say it), ingredients (list of kebab-case ids),
  allergens: map from EU-14 code to one of CONTAINS | MAY_CONTAIN | FREE.

EU-14 codes: gluten, crustaceans, eggs, fish, peanuts, soy, milk, nuts, celery, mustard,
sesame, sulphites, lupin, molluscs. "nuts" = tree nuts only (almond, hazelnut, walnut, cashew,
pecan, brazil, pistachio, macadamia). Pine nuts are NOT in "nuts".

Hard requirements:
- Include "pasta-pesto-genovese" with pine-nuts and parmesan; nuts: FREE, milk: CONTAINS.
- Include "pesto-rosso" (sun-dried tomato pesto with almonds; nuts: CONTAINS).
- Include one dessert with nuts: MAY_CONTAIN.
- Include one dish with peanuts: CONTAINS and nuts: FREE.
- Include "special-of-the-week" with ingredients but WITHOUT an allergens map.
- Every other item must list all 14 allergen codes explicitly.
Output only YAML.
```

> [!WARNING]
> Wygenerowane alergeny są **fikcyjne**, ale muszą być spójne ze składnikami. Po generacji uruchom walidator `seed.py --check`: (a) każdy składnik ma pokrycie w alergenach, (b) `CONTAINS` wynika z co najmniej jednego składnika, (c) pozycje bez mapy są dokładnie te zamierzone. To jest „verified allergen field” z wymagań — weryfikacją jest walidator + review, nie LLM.

## Mapowanie synonimów alergenów (deterministyczne, `domain/allergens.py`)

| Klient mówi | Kod |
|---|---|
| nuts, tree nuts, walnuts, almonds, hazelnuts, cashews, pistachios | `nuts` |
| peanuts, groundnuts | `peanuts` |
| gluten, wheat, flour | `gluten` |
| dairy, lactose, milk, cheese | `milk` |
| shellfish, shrimp, prawns, crab, lobster | `crustaceans` |
| mussels, clams, squid, octopus | `molluscs` |
| egg(s) | `eggs` |
| … (pozostałe 1:1) | |
| coś spoza listy (np. „nightshades”, „garlic”) | `None` → odpowiedź: nie śledzimy tego w zweryfikowanych danych → oferta handoffu |

Synonimy zawierające składnik (np. „pine nuts”) są dodatkowo sprawdzane w `ingredients` — odpowiedź zawiera informację o składniku, nie o kategorii alergenu.
