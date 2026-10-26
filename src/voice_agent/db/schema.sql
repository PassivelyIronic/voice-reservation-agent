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
