"""
JAL (Japan Airlines) fare scraper.

JAL's international booking site is a JavaScript-heavy SPA.  This module
uses Playwright to drive a real browser through the search flow:

    1. Navigate to JAL's international booking page.
    2. Fill origin, destination, dates, cabin class.
    3. Submit the search.
    4. Wait for results to render.
    5. Extract nonstop itineraries with price, flight number,
       times, and — critically — the operating carrier.

Because airline websites change without notice, selectors are grouped
at the top of the file for easy maintenance.  If a selector breaks,
update it here rather than hunting through the automation logic.

IMPORTANT:  Run this against the live site with headless=False first
to visually verify that the selectors still match.  Do not guess.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from playwright.sync_api import Page, expect

from airlines.base import AirlineScraper, FareResult

logger = logging.getLogger(__name__)


# ── JAL URL templates ──────────────────────────────────────────────────────
#
# JAL's international search can be driven via a URL with query params.
# This avoids needing to interact with the calendar widget for dates.
#
# Pattern (observed as of 2024-2025, subject to change):
#   https://www.jal.co.jp/en/inter/fare/RT/{origin}/{destination}/{dep_yyyymmdd}/{ret_yyyymmdd}/1/0/0/Y
#
# Where the trailing segments are: adults / children / infants / cabin (Y=economy).
#
# If JAL changes this pattern, fall back to interactive form filling
# by returning None from build_search_url and implementing run_search.

JAL_SEARCH_URL = (
    "https://www.jal.co.jp/en/inter/fare/RT"
    "/{origin}/{destination}/{dep_date}/{ret_date}/1/0/0/Y"
)

# Alternatively, JAL offers a booking widget URL:
JAL_BOOKING_URL = "https://www.jal.co.jp/en/inter/"


# ── CSS selectors (update these when the site changes) ─────────────────────
#
# These are PLACEHOLDERS.  The first time you run on your Mac with
# headless=False, the scraper will dump the page structure to help you
# fill in the real selectors.  See _discover_selectors() below.

class Selectors:
    """CSS / XPath selectors for the JAL results page."""

    # --- Search form (fallback interactive mode) ---
    ORIGIN_INPUT = 'input[name="origin"], #departureAirport, [data-testid="origin"]'
    DEST_INPUT = 'input[name="destination"], #arrivalAirport, [data-testid="destination"]'
    DEPART_DATE = '#departDate, [data-testid="depart-date"]'
    RETURN_DATE = '#returnDate, [data-testid="return-date"]'
    SEARCH_BUTTON = 'button[type="submit"], #searchButton, [data-testid="search-btn"]'

    # --- Results page ---
    # Container for each flight option / itinerary card
    FLIGHT_CARD = '.flight-result, .fare-result, [data-testid="flight-card"]'

    # Within a flight card:
    PRICE = '.price, .fare-amount, [data-testid="price"]'
    FLIGHT_NUMBER = '.flight-number, .flight-no, [data-testid="flight-number"]'
    DEPARTURE_TIME = '.departure-time, .depart-time, [data-testid="dep-time"]'
    ARRIVAL_TIME = '.arrival-time, .arrive-time, [data-testid="arr-time"]'
    OPERATING_CARRIER = '.operating-carrier, .operated-by, [data-testid="operator"]'
    AIRCRAFT_TYPE = '.aircraft, .equipment, [data-testid="aircraft"]'
    STOPS = '.stops, .stop-count, [data-testid="stops"]'

    # Loading / no-results indicators
    LOADING_SPINNER = '.loading, .spinner, [data-testid="loading"]'
    NO_RESULTS = '.no-results, .no-flights, [data-testid="no-results"]'


# ── Scraper ────────────────────────────────────────────────────────────────

class JALScraper(AirlineScraper):
    """Playwright-based scraper for JAL international fares."""

    def build_search_url(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> str | None:
        """
        Build a direct JAL search URL.

        Returns the URL string, or None to fall back to interactive mode.
        """
        return JAL_SEARCH_URL.format(
            origin=origin.upper(),
            destination=destination.upper(),
            dep_date=depart_date.strftime("%Y%m%d"),
            ret_date=return_date.strftime("%Y%m%d"),
        )

    def run_search(
        self,
        page: Page,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> None:
        """
        If build_search_url returned a direct link, the page should
        already be loading results.  Wait for them to appear.

        If the direct URL no longer works, this method can be expanded
        to fill the search form interactively.
        """
        # Wait for either results or a no-results indicator.
        # Give the SPA up to the configured timeout to render.
        try:
            page.wait_for_load_state("networkidle", timeout=self.timeout)
        except Exception:
            logger.warning("Network did not reach idle; continuing anyway.")

        # Attempt to wait for flight cards to appear.
        try:
            page.wait_for_selector(
                Selectors.FLIGHT_CARD,
                timeout=self.timeout,
                state="visible",
            )
            logger.info("Flight results loaded.")
        except Exception:
            # Maybe no results, or selectors are stale.
            logger.warning(
                "No flight cards found with selector '%s'. "
                "Running selector discovery...",
                Selectors.FLIGHT_CARD,
            )
            self._discover_selectors(page)

    def parse_results(
        self,
        page: Page,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> list[FareResult]:
        """
        Extract nonstop fares from the loaded JAL results page.
        """
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        results: list[FareResult] = []

        cards = page.query_selector_all(Selectors.FLIGHT_CARD)
        if not cards:
            logger.warning("No flight cards found on page.")
            self._discover_selectors(page)
            return results

        for card in cards:
            try:
                fare = self._parse_one_card(
                    card, page, origin, destination,
                    depart_date, return_date, timestamp,
                )
                if fare:
                    results.append(fare)
            except Exception:
                logger.exception("Failed to parse a flight card.")

        return results

    # ── Helpers ────────────────────────────────────────────────────────

    def _parse_one_card(
        self,
        card,
        page: Page,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
        timestamp: str,
    ) -> FareResult | None:
        """Parse a single flight-result card into a FareResult."""

        def text(selector: str) -> str:
            el = card.query_selector(selector)
            return el.inner_text().strip() if el else ""

        # Skip flights with stops.
        stops_text = text(Selectors.STOPS)
        if stops_text and "nonstop" not in stops_text.lower() and stops_text != "0":
            return None

        # Price — strip currency symbols and commas.
        raw_price = text(Selectors.PRICE)
        price_digits = re.sub(r"[^\d.]", "", raw_price)
        if not price_digits:
            return None
        price = float(price_digits)

        # Detect currency from the raw price string.
        currency = "USD"
        if "¥" in raw_price or "JPY" in raw_price.upper():
            currency = "JPY"

        flight_number = text(Selectors.FLIGHT_NUMBER)
        dep_time = text(Selectors.DEPARTURE_TIME)
        arr_time = text(Selectors.ARRIVAL_TIME)
        aircraft = text(Selectors.AIRCRAFT_TYPE)

        # Operating carrier — the key distinction this project cares about.
        op_carrier_text = text(Selectors.OPERATING_CARRIER)
        operating_carrier = self._normalize_carrier(op_carrier_text)
        marketing_carrier = self.config.name  # searched on JAL's site

        return FareResult(
            price=price,
            currency=currency,
            origin=origin,
            destination=destination,
            outbound_date=depart_date.isoformat(),
            outbound_departure_time=dep_time,
            outbound_arrival_time=arr_time,
            outbound_flight_number=flight_number,
            outbound_marketing_carrier=marketing_carrier,
            outbound_operating_carrier=operating_carrier or marketing_carrier,
            outbound_aircraft=aircraft,
            return_date=return_date.isoformat(),
            return_departure_time="",   # filled when parsing return leg
            return_arrival_time="",
            return_flight_number="",
            return_marketing_carrier=marketing_carrier,
            return_operating_carrier="",
            return_aircraft="",
            source="jal.co.jp",
            search_timestamp=timestamp,
        )

    @staticmethod
    def _normalize_carrier(raw: str) -> str:
        """
        Normalize operating-carrier text to a clean airline name.

        Examples:
            "Operated by American Airlines"  -> "American Airlines"
            "JAL operated"                   -> "Japan Airlines"
            ""                               -> ""
        """
        if not raw:
            return ""
        # Strip common prefixes.
        cleaned = re.sub(
            r"(?i)^operated\s+by\s+", "", raw
        ).strip()
        # Map common abbreviations.
        abbrev_map = {
            "JAL": "Japan Airlines",
            "ANA": "All Nippon Airways",
            "AA": "American Airlines",
            "UA": "United Airlines",
            "DL": "Delta Air Lines",
            "NH": "All Nippon Airways",
            "JL": "Japan Airlines",
        }
        return abbrev_map.get(cleaned.upper(), cleaned)

    def _discover_selectors(self, page: Page) -> None:
        """
        Diagnostic helper: when the expected selectors don't match,
        dump useful information about the actual page structure
        so a developer can update the Selectors class.

        This is NOT meant to auto-fix selectors — it's a debugging
        aid that honours the README's "do not guess" principle.
        """
        logger.info("=== SELECTOR DISCOVERY (page snapshot) ===")
        logger.info("Current URL: %s", page.url)
        logger.info("Page title: %s", page.title())

        # Save a screenshot for visual inspection.
        try:
            screenshot_path = "output/jal_debug_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            logger.info("Screenshot saved: %s", screenshot_path)
        except Exception:
            logger.warning("Could not save screenshot.")

        # Dump top-level structural elements to help find the right selectors.
        try:
            structure = page.evaluate("""() => {
                const walk = (el, depth) => {
                    if (depth > 3) return '';
                    const tag = el.tagName?.toLowerCase() || '';
                    const id = el.id ? '#' + el.id : '';
                    const cls = el.className && typeof el.className === 'string'
                        ? '.' + el.className.trim().split(/\\s+/).join('.')
                        : '';
                    const dataAttrs = Array.from(el.attributes || [])
                        .filter(a => a.name.startsWith('data-'))
                        .map(a => `[${a.name}="${a.value}"]`)
                        .join('');
                    const indent = '  '.repeat(depth);
                    let result = `${indent}<${tag}${id}${cls}${dataAttrs}>\\n`;
                    for (const child of el.children || []) {
                        result += walk(child, depth + 1);
                    }
                    return result;
                };
                return walk(document.body, 0);
            }""")
            # Truncate to avoid enormous logs.
            if len(structure) > 5000:
                structure = structure[:5000] + "\n... (truncated)"
            logger.info("Page structure:\n%s", structure)
        except Exception:
            logger.warning("Could not extract page structure.")

        # Also save raw HTML snippet for offline inspection.
        try:
            html_path = "output/jal_debug_page.html"
            content = page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Full HTML saved: %s", html_path)
        except Exception:
            logger.warning("Could not save HTML content.")

        logger.info("=== END SELECTOR DISCOVERY ===")
