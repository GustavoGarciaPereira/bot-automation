#!/usr/bin/env python3
"""Manual validation — OLX Brasil scraper with debug HTML saving.

Usage::
    python scripts/test_olx_real.py --visible
    python scripts/test_olx_real.py --visible --debug
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

    parser = argparse.ArgumentParser(description="Test OLX scraper")
    parser.add_argument("--query", default="notebook dell")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Save HTML + items for analysis")
    args = parser.parse_args()

    from src.plugins.olx.scraper import OLXScraper, _clear_config_cache
    from selenium.webdriver.common.by import By

    _clear_config_cache()
    scraper = OLXScraper(headless=not args.visible)

    print(f"\n🔍 OLX: '{args.query}'  |  Max: {args.max}")
    if args.debug:
        print("   💾 Debug mode: will save HTML + item samples")
    print()

    # If debug, run a special session first to capture HTML
    if args.debug:
        from src.plugins.base_selenium_plugin import selenium_driver
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        print("   Capturing page HTML for analysis...")
        async with selenium_driver(headless=not args.visible) as driver:
            sanitized = args.query.strip().lower().replace(" ", "-")
            url = f"https://www.olx.com.br/brasil?q={sanitized}"
            driver.get(url)
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid], main, section"))
                )
            except Exception:
                pass
            import time
            time.sleep(3)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = Path("data/logs")
            log_dir.mkdir(parents=True, exist_ok=True)

            # Full page HTML
            html_path = log_dir / f"olx_debug_{ts}.html"
            html_path.write_text(driver.page_source, encoding="utf-8")
            print(f"   ✅ Page HTML → {html_path} ({html_path.stat().st_size / 1024:.0f} KB)")

            # Screenshot
            driver.save_screenshot(str(log_dir / f"olx_debug_{ts}.png"))
            print(f"   ✅ Screenshot → data/logs/olx_debug_{ts}.png")

            # Individual items
            for selector in ["div[data-testid='ad-card']", "div.ad-card", "div[class*='AdCard']", "li", "div[class*='card']"]:
                items = driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    print(f"   Found {len(items)} items with '{selector}'")
                    items_dir = log_dir / f"olx_items_{ts}"
                    items_dir.mkdir(exist_ok=True)
                    for i, item in enumerate(items[:5]):
                        try:
                            outer = item.get_attribute("outerHTML") or item.text
                            ext = ".html" if "outerHTML" in dir(item) else ".txt"
                            (items_dir / f"item_{i}{ext}").write_text(outer, encoding="utf-8")
                        except Exception:
                            pass
                    print(f"   ✅ Sample items → {items_dir}/")
                    break
            print()

    results = await scraper.search(args.query, max_results=args.max)

    if not results:
        print("❌ No ads found.")
        sys.exit(1)

    print(f"✅ {len(results)} ads found\n")
    for i, a in enumerate(results, 1):
        title = a.get("title", "?")[:60]
        price = a.get("price", "N/A")
        location = a.get("location", "N/A")
        date = a.get("date", "N/A")
        print(f"  {i}. {title}")
        print(f"     💰 R$ {price}  |  📍 {location}  |  📅 {date}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
