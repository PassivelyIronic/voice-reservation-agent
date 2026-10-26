"""Business rules from docs/plan/04-data-model.md ("Reguły biznesowe") and 05 (search_menu)."""

from datetime import timedelta

BOOKING_WINDOW_DAYS = 30
MIN_LEAD_TIME = timedelta(minutes=60)
MIN_PARTY_SIZE = 1
MAX_PARTY_SIZE = 8
HOLD_TTL = timedelta(minutes=5)
RESERVATION_DURATION = timedelta(minutes=120)
SLOT_GRID = timedelta(minutes=15)
ALTERNATIVES_SPAN = timedelta(minutes=90)
MAX_ALTERNATIVES = 3

# No 0/O/1/I: easy to read back by voice.
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 4

MENU_EXACT_SCORE = 85.0
MENU_EXACT_MARGIN = 10.0
MENU_MAX_CANDIDATES = 3
