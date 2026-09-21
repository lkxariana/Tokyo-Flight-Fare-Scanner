"""
Configuration for Tokyo Fare Scanner.

All search parameters, route definitions, and output settings live here.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


# ── Travel window ──────────────────────────────────────────────────────────

# Outbound: depart a U.S. airport between these two timestamps (local time).
#   2026-12-17 00:00  <=  departure  <=  2026-12-18 03:00
OUTBOUND_DATES: list[date] = [
    date(2026, 12, 17),
    date(2026, 12, 18),  # only flights departing by 03:00 local
]

OUTBOUND_LATEST_HOUR_DEC18 = 3  # cut-off hour on Dec 18

# Return: depart Tokyo on either of these dates, any time.
RETURN_DATES: list[date] = [
    date(2027, 1, 15),
    date(2027, 1, 16),
]


# ── Airports ───────────────────────────────────────────────────────────────

TOKYO_AIRPORTS: list[str] = ["HND", "NRT"]

# U.S. airports with known nonstop service to Tokyo.
# This list should be verified against each airline's actual route map.
US_AIRPORTS: list[str] = [
    "LAX",  # Los Angeles
    "SFO",  # San Francisco
    "SEA",  # Seattle
    "ORD",  # Chicago O'Hare
    "JFK",  # New York JFK
    "EWR",  # Newark
    "IAD",  # Washington Dulles
    "IAH",  # Houston
    "DFW",  # Dallas/Fort Worth
    "BOS",  # Boston
    "ATL",  # Atlanta
    "HNL",  # Honolulu
]


# ── Cabin / trip type ──────────────────────────────────────────────────────

CABIN_CLASS = "economy"
TRIP_TYPE = "roundtrip"
NONSTOP_ONLY = True
PASSENGERS = 1


# ── Airline-specific settings ──────────────────────────────────────────────

@dataclass
class AirlineConfig:
    """Per-airline settings."""
    name: str
    code: str                       # IATA 2-letter code
    enabled: bool = True
    base_url: str = ""
    # Subset of US_AIRPORTS this airline actually serves nonstop to Tokyo.
    # Empty list means "try all US_AIRPORTS" (will be refined later).
    routes: list[str] = field(default_factory=list)


AIRLINES: dict[str, AirlineConfig] = {
    "jal": AirlineConfig(
        name="Japan Airlines",
        code="JL",
        base_url="https://www.jal.co.jp/en/",
        routes=[],  # to be verified
    ),
    "ana": AirlineConfig(
        name="All Nippon Airways",
        code="NH",
        enabled=False,  # stage 6
        base_url="https://www.ana.co.jp/en/us/",
        routes=[],
    ),
    "american": AirlineConfig(
        name="American Airlines",
        code="AA",
        enabled=False,  # stage 7
        base_url="https://www.aa.com/",
        routes=[],
    ),
    "united": AirlineConfig(
        name="United Airlines",
        code="UA",
        enabled=False,  # stage 7
        base_url="https://www.united.com/",
        routes=[],
    ),
    "delta": AirlineConfig(
        name="Delta Air Lines",
        code="DL",
        enabled=False,  # stage 7
        base_url="https://www.delta.com/",
        routes=[],
    ),
}


# ── Browser / Playwright ──────────────────────────────────────────────────

# On macOS, use the locally installed Chrome:
#   /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
# In CI or cloud, leave as None to use Playwright's bundled Chromium.
CHROME_EXECUTABLE: str | None = None

HEADLESS = True          # flip to False for local debugging
SLOW_MO = 0              # ms delay between Playwright actions (debugging)
PAGE_TIMEOUT = 60_000    # ms to wait for navigation / selectors


# ── Output ─────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_CSV = OUTPUT_DIR / "fares.csv"

# Fields written to the CSV (column order).
CSV_COLUMNS: list[str] = [
    "price",
    "currency",
    "origin",
    "destination",
    "outbound_date",
    "outbound_departure_time",
    "outbound_arrival_time",
    "outbound_flight_number",
    "outbound_marketing_carrier",
    "outbound_operating_carrier",
    "outbound_aircraft",
    "return_date",
    "return_departure_time",
    "return_arrival_time",
    "return_flight_number",
    "return_marketing_carrier",
    "return_operating_carrier",
    "return_aircraft",
    "source",
    "search_timestamp",
]
