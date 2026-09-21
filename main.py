#!/usr/bin/env python3
"""
Tokyo Fare Scanner — main entry point.

Searches official airline booking websites for nonstop round-trip
economy tickets from U.S. airports to Tokyo, then produces a
price-sorted table and CSV.

Usage:
    python main.py                  # run all enabled airlines
    python main.py --airline jal    # run JAL only
    python main.py --visible        # run with browser visible (headless=False)
    python main.py --discover       # inspect page structure, don't parse
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import config
from airlines.base import FareResult
from airlines.jal import JALScraper

# ── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scanner")


# ── Registry of airline scrapers ───────────────────────────────────────────

SCRAPER_CLASSES: dict[str, type] = {
    "jal": JALScraper,
    # "ana": ANAScraper,        # stage 6
    # "american": AAScraper,    # stage 7
    # "united": UAScraper,      # stage 7
    # "delta": DLScraper,       # stage 7
}


def build_scraper(key: str, *, headless: bool) -> "airlines.base.AirlineScraper":
    """Instantiate a scraper for the given airline key."""
    cls = SCRAPER_CLASSES[key]
    cfg = config.AIRLINES[key]
    return cls(
        airline_config=cfg,
        headless=headless,
        executable_path=config.CHROME_EXECUTABLE,
        slow_mo=config.SLOW_MO,
        timeout=config.PAGE_TIMEOUT,
    )


# ── Main logic ─────────────────────────────────────────────────────────────

def run(*, airlines: list[str] | None = None, headless: bool = True) -> pd.DataFrame:
    """
    Execute fare searches and return a DataFrame of results.

    Parameters
    ----------
    airlines
        List of airline keys to search (e.g. ["jal"]).
        None means all enabled airlines.
    headless
        Whether to run the browser in headless mode.
    """
    if airlines is None:
        airlines = [
            key for key, cfg in config.AIRLINES.items()
            if cfg.enabled and key in SCRAPER_CLASSES
        ]

    all_fares: list[dict] = []

    for key in airlines:
        if key not in SCRAPER_CLASSES:
            logger.warning("No scraper implemented for '%s', skipping.", key)
            continue
        if key not in config.AIRLINES:
            logger.warning("No config for '%s', skipping.", key)
            continue

        cfg = config.AIRLINES[key]
        print(f"{cfg.name:.<30s} ", end="", flush=True)

        scraper = build_scraper(key, headless=headless)
        results = scraper.search_all(
            us_airports=config.US_AIRPORTS,
            tokyo_airports=config.TOKYO_AIRPORTS,
            outbound_dates=config.OUTBOUND_DATES,
            return_dates=config.RETURN_DATES,
        )

        all_fares.extend(r.as_dict() for r in results)
        print(f" {len(results)} fares found")

    if not all_fares:
        logger.info("No fares collected.")
        return pd.DataFrame(columns=config.CSV_COLUMNS)

    df = pd.DataFrame(all_fares, columns=config.CSV_COLUMNS)
    df.sort_values("price", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def save_csv(df: pd.DataFrame) -> Path:
    """Write results to the output CSV."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.OUTPUT_CSV, index=False)
    logger.info("Saved %d rows to %s", len(df), config.OUTPUT_CSV)
    return config.OUTPUT_CSV


def print_table(df: pd.DataFrame) -> None:
    """Print a human-readable summary table to stdout."""
    if df.empty:
        print("\nNo fares found.")
        return

    print("\n" + "=" * 78)
    print(f"{'PRICE':>8}  {'ROUTE':<10}  {'OUTBOUND':<28}  {'OPERATED BY'}")
    print("-" * 78)

    for _, row in df.iterrows():
        price_str = f"${row['price']:,.0f}" if row["currency"] == "USD" else f"{row['price']:,.0f} {row['currency']}"
        route = f"{row['origin']}-{row['destination']}"
        outbound = f"{row['outbound_date'][5:]} {row['outbound_departure_time']} {row['outbound_flight_number']}"
        op_out = row["outbound_operating_carrier"]
        op_ret = row["return_operating_carrier"]
        operated = f"{op_out} / {op_ret}" if op_ret else op_out
        print(f"{price_str:>8}  {route:<10}  {outbound:<28}  {operated}")

    print("=" * 78)
    print(f"\n{len(df)} itineraries found.\n")


# ── CLI ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search airline websites for nonstop flights to Tokyo.",
    )
    parser.add_argument(
        "--airline", "-a",
        action="append",
        choices=list(SCRAPER_CLASSES.keys()),
        help="Run only this airline (can be repeated).",
    )
    parser.add_argument(
        "--visible", "-v",
        action="store_true",
        help="Show the browser window (headless=False).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't write the output CSV.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("\nSearching official airline websites...\n")

    df = run(
        airlines=args.airline,
        headless=not args.visible,
    )

    print_table(df)

    if not args.no_save and not df.empty:
        save_csv(df)


if __name__ == "__main__":
    main()
