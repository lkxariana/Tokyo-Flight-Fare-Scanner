"""
Abstract base class for airline fare scrapers.

Every airline module (jal.py, ana.py, …) subclasses AirlineScraper
and implements the three abstract methods:

    build_search_url   – construct or navigate to the search form
    run_search         – fill the form, click search, wait for results
    parse_results      – extract structured fare rows from the page

The base class handles the Playwright lifecycle and the outer loop
over routes × date combinations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

if TYPE_CHECKING:
    from config import AirlineConfig

logger = logging.getLogger(__name__)


# ── Data containers ────────────────────────────────────────────────────────

@dataclass
class FareResult:
    """One bookable itinerary (outbound + return)."""

    price: float
    currency: str  # e.g. "USD"

    origin: str
    destination: str

    outbound_date: str
    outbound_departure_time: str
    outbound_arrival_time: str
    outbound_flight_number: str
    outbound_marketing_carrier: str
    outbound_operating_carrier: str
    outbound_aircraft: str

    return_date: str
    return_departure_time: str
    return_arrival_time: str
    return_flight_number: str
    return_marketing_carrier: str
    return_operating_carrier: str
    return_aircraft: str

    source: str             # e.g. "jal.co.jp"
    search_timestamp: str   # ISO-8601

    def as_dict(self) -> dict:
        """Return a flat dict matching config.CSV_COLUMNS order."""
        return {
            "price": self.price,
            "currency": self.currency,
            "origin": self.origin,
            "destination": self.destination,
            "outbound_date": self.outbound_date,
            "outbound_departure_time": self.outbound_departure_time,
            "outbound_arrival_time": self.outbound_arrival_time,
            "outbound_flight_number": self.outbound_flight_number,
            "outbound_marketing_carrier": self.outbound_marketing_carrier,
            "outbound_operating_carrier": self.outbound_operating_carrier,
            "outbound_aircraft": self.outbound_aircraft,
            "return_date": self.return_date,
            "return_departure_time": self.return_departure_time,
            "return_arrival_time": self.return_arrival_time,
            "return_flight_number": self.return_flight_number,
            "return_marketing_carrier": self.return_marketing_carrier,
            "return_operating_carrier": self.return_operating_carrier,
            "return_aircraft": self.return_aircraft,
            "source": self.source,
            "search_timestamp": self.search_timestamp,
        }


# ── Base scraper ───────────────────────────────────────────────────────────

class AirlineScraper(ABC):
    """
    Template for an airline-specific Playwright scraper.

    Subclasses must implement:
        build_search_url(origin, destination, depart_date, return_date)
        run_search(page, origin, destination, depart_date, return_date)
        parse_results(page, origin, destination, depart_date, return_date)
    """

    def __init__(
        self,
        airline_config: AirlineConfig,
        *,
        headless: bool = True,
        executable_path: str | None = None,
        slow_mo: int = 0,
        timeout: int = 60_000,
    ) -> None:
        self.config = airline_config
        self.headless = headless
        self.executable_path = executable_path
        self.slow_mo = slow_mo
        self.timeout = timeout

    # ── Abstract interface ─────────────────────────────────────────────

    @abstractmethod
    def build_search_url(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> str | None:
        """
        Return a direct-link URL that pre-fills the search form,
        or None if the airline requires interactive form filling.
        """
        ...

    @abstractmethod
    def run_search(
        self,
        page: Page,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> None:
        """
        Given a Page already navigated to the booking site,
        fill in the search form and trigger the search.
        Should wait until results are loaded before returning.
        """
        ...

    @abstractmethod
    def parse_results(
        self,
        page: Page,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> list[FareResult]:
        """
        Extract all eligible nonstop fare results from the current page.
        Return a list of FareResult objects.
        """
        ...

    # ── Outer search loop ──────────────────────────────────────────────

    def search_route(
        self,
        browser: Browser,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date,
    ) -> list[FareResult]:
        """Run one search for a single origin-destination-date combination."""
        context: BrowserContext = browser.new_context(
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )
        context.set_default_timeout(self.timeout)
        page: Page = context.new_page()

        results: list[FareResult] = []
        try:
            url = self.build_search_url(origin, destination, depart_date, return_date)
            if url:
                logger.info("Navigating to %s", url)
                page.goto(url, wait_until="domcontentloaded")
            else:
                logger.info("Navigating to %s (interactive form)", self.config.base_url)
                page.goto(self.config.base_url, wait_until="domcontentloaded")

            self.run_search(page, origin, destination, depart_date, return_date)
            results = self.parse_results(page, origin, destination, depart_date, return_date)
            logger.info(
                "%s  %s→%s  %s→%s  found %d fares",
                self.config.name, origin, destination,
                depart_date, return_date, len(results),
            )
        except Exception:
            logger.exception(
                "%s  %s→%s  %s→%s  search failed",
                self.config.name, origin, destination,
                depart_date, return_date,
            )
        finally:
            context.close()

        return results

    def search_all(
        self,
        us_airports: list[str],
        tokyo_airports: list[str],
        outbound_dates: list[date],
        return_dates: list[date],
    ) -> list[FareResult]:
        """
        Run searches across every combination of:
            origin × destination × outbound_date × return_date

        Returns all collected FareResult rows.
        """
        # If the airline config specifies its own route list, use that.
        origins = self.config.routes if self.config.routes else us_airports
        all_results: list[FareResult] = []

        with sync_playwright() as pw:
            launch_args: dict = {
                "headless": self.headless,
                "slow_mo": self.slow_mo,
            }
            if self.executable_path:
                launch_args["executable_path"] = self.executable_path

            browser = pw.chromium.launch(**launch_args)

            try:
                for origin in origins:
                    for dest in tokyo_airports:
                        for dep in outbound_dates:
                            for ret in return_dates:
                                fares = self.search_route(
                                    browser, origin, dest, dep, ret
                                )
                                all_results.extend(fares)
            finally:
                browser.close()

        return all_results
