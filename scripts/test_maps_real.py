#!/usr/bin/env python3
"""Manual validation script — runs a real Google Maps search via Selenium.

Usage::

    python scripts/test_maps_real.py                                # headless
    python scripts/test_maps_real.py --visible                      # visible
    python scripts/test_maps_real.py --visible --save-html          # + save HTML for debug
    python scripts/test_maps_real.py --query "pizzaria" --max 5
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Test Google Maps scraper")
    parser.add_argument("--query", default="dentistas em campinas sp")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--save-html", action="store_true", help="Save page HTML + screenshot for debugging")
    args = parser.parse_args()

    from src.plugins.google_maps.scraper import GoogleMapsScraper, _clear_config_cache
    from src.plugins.base_selenium_plugin import selenium_driver

    _clear_config_cache()

    scraper = GoogleMapsScraper(headless=not args.visible)

    print(f"\n🔍 Searching Google Maps for: {args.query!r}")
    print(f"   Headless: {not args.visible}  |  Max: {args.max}")

    if args.save_html:
        print(f"\n💾 Will save page HTML + screenshot to data/logs/")
        # Do a separate run just to capture the HTML
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        print("   Opening browser to save HTML for analysis...")
        async with selenium_driver(headless=not args.visible) as driver:
            search_url = f"https://www.google.com/maps/search/{args.query.replace(' ', '+')}"
            driver.get(search_url)
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='article'], div[role='feed']"))
                )
            except Exception:
                pass
            import time
            time.sleep(3)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = Path("data/logs")
            log_dir.mkdir(parents=True, exist_ok=True)

            html_path = log_dir / f"gmaps_debug_{ts}.html"
            html_path.write_text(driver.page_source, encoding="utf-8")
            print(f"   ✅ HTML salvo → {html_path} ({html_path.stat().st_size / 1024:.0f} KB)")

            shot_path = log_dir / f"gmaps_debug_{ts}.png"
            driver.save_screenshot(str(shot_path))
            print(f"   ✅ Screenshot salvo → {shot_path}")

            # Also save a sample item HTML
            items = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
            if items:
                sample_dir = log_dir / f"gmaps_items_{ts}"
                sample_dir.mkdir(exist_ok=True)
                for i, item in enumerate(items[:10]):
                    try:
                        outer = item.get_attribute("outerHTML") or item.text
                        (sample_dir / f"item_{i+1}.html").write_text(outer, encoding="utf-8")
                    except Exception:
                        pass
                print(f"   ✅ {min(10, len(items))} sample items salvos → {sample_dir}/")
            print()
    else:
        print()

    results = await scraper.search(args.query, max_results=args.max)

    if not results:
        print("❌ No businesses found.")
        print("   Check data/logs/ for debug screenshots and HTML files.")
        sys.exit(1)

    print(f"✅ {len(results)} businesses found\n")
    for i, b in enumerate(results, 1):
        name = b.get("name", "?")
        rating = b.get("rating", "N/A")
        reviews = b.get("reviews_count", "?")
        address = b.get("address", "N/A")
        phone = b.get("phone", "N/A")
        website = b.get("website", "N/A")
        print(f"  {i}. {name}")
        print(f"     ⭐ {rating} ({reviews} avaliações)")
        print(f"     📍 {address}")
        print(f"     📞 {phone}")
        print(f"     🌐 {website}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
