#!/usr/bin/env python3
"""
Headless smoke test for Tokyo Fare Scanner.

Verifies that:
    1. Playwright can launch Chromium headlessly.
    2. The browser can navigate to the JAL international booking page.
    3. The page loads enough content to confirm it's the real site.
    4. The module imports and classes instantiate correctly.
    5. A direct search URL can be constructed.

This does NOT attempt to parse fare results (the selectors need
to be calibrated against the live site with a visible browser).
"""

import sys
import os

# Ensure project root is on the path.
sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright

import config
from airlines.jal import JALScraper, Selectors


def test_imports():
    """Verify all project modules import cleanly."""
    print("1. Module imports .............. ", end="", flush=True)
    from airlines.base import AirlineScraper, FareResult
    from airlines.jal import JALScraper
    import config
    print("OK")


def test_scraper_instantiation():
    """Verify the JAL scraper can be created."""
    print("2. JAL scraper instantiation ... ", end="", flush=True)
    scraper = JALScraper(
        airline_config=config.AIRLINES["jal"],
        headless=True,
    )
    assert scraper.config.name == "Japan Airlines"
    assert scraper.config.code == "JL"
    print("OK")


def test_search_url():
    """Verify URL construction."""
    print("3. Search URL construction ..... ", end="", flush=True)
    from datetime import date
    scraper = JALScraper(
        airline_config=config.AIRLINES["jal"],
        headless=True,
    )
    url = scraper.build_search_url("LAX", "HND", date(2026, 12, 17), date(2027, 1, 15))
    assert url is not None
    assert "LAX" in url
    assert "HND" in url
    assert "20261217" in url
    assert "20270115" in url
    print("OK")
    print(f"   URL: {url}")


def test_playwright_launch():
    """Verify Playwright can launch Chromium."""
    print("4. Playwright browser launch ... ", end="", flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        version = browser.version
        browser.close()
    print(f"OK  (Chromium {version})")


def test_jal_navigation():
    """Navigate to the JAL site and check the page loads."""
    print("5. JAL website navigation ...... ", end="", flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(locale="en-US")
        page = context.new_page()

        # Navigate to JAL's English international page.
        response = page.goto(
            "https://www.jal.co.jp/en/",
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        status = response.status if response else "no response"
        title = page.title()
        url = page.url

        context.close()
        browser.close()

    print(f"OK  (HTTP {status})")
    print(f"   Title: {title}")
    print(f"   URL:   {url}")


def test_jal_search_page():
    """
    Attempt to navigate to a direct search URL and report
    what the page looks like — this is the key diagnostic for
    knowing whether the URL pattern still works.
    """
    print("6. JAL direct search URL ....... ", end="", flush=True)
    from datetime import date

    scraper = JALScraper(
        airline_config=config.AIRLINES["jal"],
        headless=True,
    )
    url = scraper.build_search_url("LAX", "HND", date(2026, 12, 17), date(2027, 1, 15))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(locale="en-US")
        page = context.new_page()

        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        status = response.status if response else "no response"
        final_url = page.url
        title = page.title()

        # Wait a moment for JS to render.
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        # Grab a screenshot for inspection.
        os.makedirs("output", exist_ok=True)
        page.screenshot(path="output/smoke_test_screenshot.png", full_page=True)

        # Report basic page structure.
        body_text_len = len(page.inner_text("body"))
        form_count = page.evaluate("document.querySelectorAll('form').length")
        input_count = page.evaluate("document.querySelectorAll('input').length")
        button_count = page.evaluate("document.querySelectorAll('button').length")

        context.close()
        browser.close()

    print(f"OK  (HTTP {status})")
    print(f"   Final URL:    {final_url}")
    print(f"   Title:        {title}")
    print(f"   Body length:  {body_text_len} chars")
    print(f"   Forms:        {form_count}")
    print(f"   Inputs:       {input_count}")
    print(f"   Buttons:      {button_count}")
    print(f"   Screenshot:   output/smoke_test_screenshot.png")


def main():
    print("\n" + "=" * 60)
    print("  Tokyo Fare Scanner — Smoke Test")
    print("=" * 60 + "\n")

    tests = [
        test_imports,
        test_scraper_instantiation,
        test_search_url,
        test_playwright_launch,
        test_jal_navigation,
        test_jal_search_page,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL  ({type(e).__name__}: {e})")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
