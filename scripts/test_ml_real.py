#!/usr/bin/env python3
"""Manual validation script — runs a real Mercado Livre search via Selenium.

Usage::

    python scripts/test_ml_real.py              # headless
    python scripts/test_ml_real.py --visible     # visible browser
    python scripts/test_ml_real.py --debug       # headless + save HTML/screenshots
    python scripts/test_ml_real.py --visible --debug  # visible + debug
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Test ML scraper with real Selenium")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--debug", action="store_true", help="Save debug artifacts")
    args = parser.parse_args()

    headless = not args.visible
    debug = args.debug

    from src.plugins.mercado_livre.scraper import MercadoLivreScraper, _clear_config_cache

    _clear_config_cache()

    scraper = MercadoLivreScraper(headless=headless)
    query = "notebook dell"
    max_results = 5

    print(f"\n🔍 Searching Mercado Livre for: {query!r}")
    print(f"   Headless: {headless}  |  Debug: {debug}")
    print(f"   Timeout: {scraper._cfg.get('timeout_seconds', 30)}s")
    print()

    results = await scraper.search(query, max_results=max_results)

    if not results:
        print("❌ No products found.")
        print("   Check data/logs/ for debug screenshots and HTML files.")
        sys.exit(1)

    print(f"✅ {len(results)} products found\n")
    for i, p in enumerate(results, 1):
        title = p.get("title", "?")[:60]
        price = p.get("price", 0)
        free = p.get("free_shipping", False)
        url = p.get("url", "")[:80]
        print(f"  {i}. {title}")
        print(f"     R$ {price:.2f}  |  Frete grátis: {free}")
        if url:
            print(f"     {url}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
