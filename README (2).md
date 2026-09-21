# Tokyo Fare Scanner

A personal Python experiment for searching and comparing nonstop flights from the United States to Tokyo using official airline booking websites.

## What it does

Instead of relying on Google Flights or Expedia, this program uses [Playwright](https://playwright.dev/python/) to drive a real browser through airline booking sites — the same way a person would search manually. It fills in the search form, waits for results, and extracts structured fare data including the **operating carrier** (not just the marketing codeshare).

The output is a price-sorted table of nonstop round-trip economy itineraries.

## Search parameters

- **Outbound:** Dec 17, 2026 (any time) through Dec 18, 2026 (by 03:00 local)
- **Return:** Jan 15 or Jan 16, 2027
- **Cabin:** Economy, 1 passenger, nonstop only
- **Tokyo airports:** HND (Haneda), NRT (Narita)
- **U.S. airports:** LAX, SFO, SEA, ORD, JFK, EWR, IAD, IAH, DFW, BOS, ATL, HNL

## Project structure

```
tokyo_fare_scanner/
├── config.py              # search parameters, airline configs, browser settings
├── main.py                # CLI entry point
├── smoke_test.py          # verifies Playwright + browser work correctly
├── requirements.txt
├── airlines/
│   ├── __init__.py
│   ├── base.py            # abstract base scraper + FareResult dataclass
│   └── jal.py             # Japan Airlines scraper (first target)
└── output/
    └── fares.csv           # generated results (git-ignored)
```

## Setup (macOS)

```bash
cd tokyo_fare_scanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

No need to install Playwright's bundled browser — the project uses your existing Chrome:

```python
# config.py
CHROME_EXECUTABLE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HEADLESS = False  # set True once selectors are calibrated
```

## Usage

Run the smoke test first:

```bash
python smoke_test.py
```

Then search:

```bash
python main.py                  # all enabled airlines
python main.py --airline jal    # JAL only
python main.py --visible        # show the browser window
```

Results are printed as a table and saved to `output/fares.csv`.

## Development approach

The project is built one airline at a time. CSS selectors are **placeholders** until calibrated against the live site — the scraper includes a `_discover_selectors()` method that saves a screenshot and full HTML dump for inspection rather than guessing.

**Current stage:** JAL scraper scaffolded, selectors need calibration.

### Roadmap

1. ~~Project structure~~ ✓
2. ~~Base scraper class~~ ✓
3. ~~JAL module~~ ✓ (selectors pending)
4. Calibrate JAL selectors against live site
5. Expand to multiple routes
6. Add ANA
7. Add American, United, Delta
8. Combine and sort all results

## Design principles

- **Do not guess selectors.** Inspect the actual page first.
- **Operating carrier matters.** A JAL codeshare operated by American Airlines is recorded as such.
- **No third-party aggregators.** Only official airline booking sites.
- **Stop on CAPTCHA.** Don't try to circumvent restrictions.

## Requirements

- Python 3.11+
- Google Chrome (macOS) or Chromium
- See `requirements.txt`
