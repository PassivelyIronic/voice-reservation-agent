---
title: Specyfikacja narzędzi
tags: [voice-ai, tools, tool-calling]
updated: 2026-10-26
---

# 05 — Specyfikacja narzędzi (tool definitions)

## Zasady projektowe

1. **Narzędzie = cienki adapter** nad `domain/`. Zero logiki biznesowej w handlerze — tylko parsowanie argumentów, wywołanie domeny, serializacja wyniku.
2. **Jednolita koperta wyniku:**
   ```json
   {"ok": true,  "data": { ... }}
   {"ok": false, "error": {"code": "NO_AVAILABILITY", "agent_hint": "Offer the alternatives.", "retryable": false}}
   ```
   `agent_hint` to krótka instrukcja dla LLM (po angielsku), nie tekst dla klienta.
3. **Tekst dla klienta tam, gdzie liczy się precyzja, pochodzi z narzędzia** (`readback`, `spoken_answer`) — renderowany szablonem.
4. **Preconditions egzekwowane w serwerze**, nie w prompcie (prompt tylko je opisuje).
5. **Schematy w jednym miejscu** (`tools/schemas.py`, Pydantic → JSON Schema), z nich generowane: definicje dla LLM, dokumentacja w README, walidacja argumentów.
6. **Timeout 2 s na handler**; `sqlite3.OperationalError` (locked) → 1 retry po 100 ms; błędy domenowe nie są retryowane.

## Katalog

| Narzędzie | Efekt uboczny | Wymaga |
|---|---|---|
| `get_restaurant_info` | brak | — |
| `check_availability` | **tworzy hold** (5 min) | — |
| `create_reservation` | **tworzy rezerwację** | aktywny `hold_id` z tej rozmowy, utworzony we **wcześniejszej** turze |
| `search_menu` | brak | — |
| `get_allergen_info` | brak | `item_id` z `search_menu` |
| `transfer_to_human` | tworzy ticket, kończy obsługę przez bota | — |

## Definicje

### `get_restaurant_info`
```json
{
  "name": "get_restaurant_info",
  "description": "Get verified restaurant facts: opening hours, address, parking, policies. Use instead of answering from memory.",
  "parameters": {
    "type": "object",
    "properties": {
      "topic": {"type": "string", "enum": ["opening_hours", "address", "parking", "large_groups", "dress_code", "accessibility"]},
      "date": {"type": "string", "format": "date", "description": "Optional. For opening_hours on a specific date (YYYY-MM-DD)."}
    },
    "required": ["topic"]
  }
}
```
Wynik: `{"ok":true,"data":{"topic":"opening_hours","spoken_answer":"On Friday, October 30th we're open from noon to 11 PM; the last seating is at 9:30 PM."}}`

### `check_availability`
```json
{
  "name": "check_availability",
  "description": "Check if a table is available and place a 5-minute hold on it. Always call before create_reservation. Resolve relative dates using today's date from the system prompt.",
  "parameters": {
    "type": "object",
    "properties": {
      "date": {"type": "string", "format": "date", "description": "YYYY-MM-DD in restaurant local time"},
      "time": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$", "description": "24h HH:MM"},
      "party_size": {"type": "integer", "minimum": 1, "maximum": 20},
      "zone_preference": {"type": "string", "enum": ["any", "window", "terrace", "main"], "default": "any"}
    },
    "required": ["date", "time", "party_size"]
  }
}
```
Wynik (dostępny):
```json
{"ok": true, "data": {
  "available": true, "hold_id": "H-91AF", "hold_expires_in_s": 300,
  "date": "2026-10-27", "time": "19:30", "party_size": 4, "table_zone": "window",
  "readback": "a table for 4 on Tuesday, October 27th at 7:30 PM"
}}
```
Wynik (brak miejsc):
```json
{"ok": true, "data": {
  "available": false,
  "alternatives": [
    {"date": "2026-10-30", "time": "18:15", "readback": "Friday, October 30th at 6:15 PM"},
    {"date": "2026-10-30", "time": "21:00", "readback": "Friday, October 30th at 9 PM"}
  ]
}}
```
Kody błędów: `INVALID_DATE`, `IN_THE_PAST`, `OUT_OF_WINDOW`, `TOO_SOON`, `CLOSED` (+ `next_open`), `LARGE_PARTY` (agent_hint: transfer to human), `SLOT_GRID` (czas nie na siatce 15-min → zaokrąglenie zaproponowane w `data.suggested_time`).

> `party_size` w schemacie dopuszcza do 20, żeby LLM przekazał prawdziwą liczbę — odrzucenie (>8) odbywa się w domenie i daje deterministyczny handoff zamiast halucynacji „mamy stolik dla 12”.

### `create_reservation`
```json
{
  "name": "create_reservation",
  "description": "Confirm a held table. Only call after reading the hold back to the customer and receiving an explicit yes in a later turn.",
  "parameters": {
    "type": "object",
    "properties": {
      "hold_id": {"type": "string"},
      "customer_name": {"type": "string", "minLength": 1, "maxLength": 80},
      "phone": {"type": "string", "description": "Digits as spoken; server normalizes."},
      "notes": {"type": "string", "maxLength": 200, "description": "Only what the customer said, e.g. 'nut allergy'."}
    },
    "required": ["hold_id", "customer_name", "phone"]
  }
}
```
Wynik: `{"ok":true,"data":{"code":"OV-4F2K","readback":"You're booked: a table for 4 on Tuesday, October 27th at 7:30 PM under the name Anna. Your confirmation code is O-V, 4, F, 2, K."}}`

Kody błędów: `HOLD_NOT_FOUND`, `HOLD_EXPIRED` (agent_hint: re-check availability), `HOLD_FOREIGN` (hold z innej rozmowy), `CONFIRMATION_REQUIRED` (hold utworzony w tej samej turze — wymusza rundę potwierdzenia), `INVALID_PHONE`, `SLOT_TAKEN` (przegrany wyścig, + alternatywy).

### `search_menu`
```json
{
  "name": "search_menu",
  "description": "Find menu items by name or description. Returns item ids needed by get_allergen_info.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "category": {"type": "string", "enum": ["any", "starter", "pasta", "main", "dessert", "drink"], "default": "any"}
    },
    "required": ["query"]
  }
}
```
Implementacja: `rapidfuzz` po `name` + `aliases`; score ≥ 85 i przewaga ≥ 10 nad drugim → `match: "exact"`; inaczej `match: "ambiguous"` + do 3 kandydatów (agent dopytuje). Pozycje `is_available=0` zwracane z flagą `sold_out`.

### `get_allergen_info`
```json
{
  "name": "get_allergen_info",
  "description": "The ONLY source for allergen answers. Never state allergen facts that are not in this tool's result. Speak 'spoken_answer' as given.",
  "parameters": {
    "type": "object",
    "properties": {
      "item_id": {"type": "string"},
      "allergens": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Allergens as the customer said them, e.g. ['nuts'] or ['dairy','gluten']"}
    },
    "required": ["item_id", "allergens"]
  }
}
```
Wynik:
```json
{"ok": true, "data": {
  "item_id": "pasta-pesto-genovese", "item_name": "Pesto Genovese",
  "results": [
    {"asked": "nuts", "code": "nuts", "status": "FREE",
     "related_ingredients": [{"name": "pine nuts", "note": "Pine nuts are not classed as tree nuts, but some people with nut allergies react to them."}]}
  ],
  "spoken_answer": "According to our verified allergen records, the Pesto Genovese contains no tree nuts. It does contain pine nuts, which are not classed as tree nuts, but some people with nut allergies react to them. If your allergy is severe, I can connect you with our staff.",
  "requires_handoff_offer": true,
  "guard_token": "AG-7c1e"
}}
```
Statusy → szablony (w `dialogue/renderers.py`):

| Status | Szablon (sens) | Handoff offer |
|---|---|---|
| `CONTAINS` | „…contains {allergen}.” | nie |
| `MAY_CONTAIN` | „…may contain traces of {allergen} — it's prepared in a kitchen that handles it.” | tak |
| `FREE` | „According to our verified allergen records, … contains no {allergen}.” | tylko gdy `related_ingredients` lub klient powiedział „severe” |
| `UNKNOWN` | „I don't have verified allergen information for that dish, so I can't confirm it. I can connect you with our staff.” | tak (zawsze) |
| kod `None` (alergen spoza 14) | „We only track the 14 major allergens in our verified records…” | tak |

`guard_token` — identyfikator wyniku, który `AllergenClaimGuard` wiąże z bieżącą turą (patrz [06](06-dialogue-guardrails.md)).

### `transfer_to_human`
```json
{
  "name": "transfer_to_human",
  "description": "Hand the conversation to restaurant staff. Use for: party larger than 8, unknown or severe allergy questions the records cannot answer, complaints, explicit requests for a person, repeated tool failures, anything outside reservations/menu/hours.",
  "parameters": {
    "type": "object",
    "properties": {
      "reason": {"type": "string", "enum": ["large_party","allergen_unknown","severe_allergy","tool_failure","customer_request","complaint","out_of_scope"]},
      "summary": {"type": "string", "maxLength": 300, "description": "One-paragraph summary for staff."}
    },
    "required": ["reason", "summary"]
  }
}
```
W demo „transfer” = ticket w `handoff_tickets` + komunikat „I'm passing you to our staff now…” + zakończenie sesji bota. Metryka handoff accuracy porównuje `reason` z etykietą scenariusza.

## Fault injection (dla testów edge case)

`FAULT_INJECTION="check_availability:error:1.0,search_menu:timeout:0.3"` — wrapper w `tools/registry.py` losowo (seedowany RNG) zwraca błąd lub opóźnienie > timeout. Używane wyłącznie w scenariuszach z tagiem `fault`. Oczekiwane zachowanie: 1 ponowienie przez LLM → przeprosiny + `transfer_to_human(reason="tool_failure")`.

## Filler przy tool callu

Na zdarzenie rozpoczęcia wywołania funkcji (event handler w LLM service — sprawdź nazwę w Context Hub) pipeline wypowiada krótki filler z puli („One moment, let me check.”), tylko gdy od końca tury klienta minęło > 300 ms i w tej turze nie było jeszcze wypowiedzi bota. Mierzymy wpływ na postrzeganą latencję (time-to-first-audio) osobno od voice-to-voice.
