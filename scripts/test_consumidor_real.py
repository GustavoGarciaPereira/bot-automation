#!/usr/bin/env python3
"""Manual validation — Consumidor.gov.br scraper.

Usage::

    python scripts/test_consumidor_real.py --visible
    python scripts/test_consumidor_real.py --company "Magazine Luiza" --visible
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

    parser = argparse.ArgumentParser(description="Test Consumidor.gov.br scraper")
    parser.add_argument("--company", default="Magazine Luiza")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    from src.plugins.consumidor_gov.scraper import ConsumidorGovScraper, _clear_config_cache

    _clear_config_cache()
    scraper = ConsumidorGovScraper(headless=not args.visible)

    print(f"\n🔍 Scraping Consumidor.gov.br for: '{args.company}'")
    print(f"   Headless: {not args.visible}  |  Max pages: {args.pages}")
    print()

    results = await scraper.search(args.company, max_pages=args.pages)

    if not results:
        print("❌ No complaints found.")
        sys.exit(1)

    print(f"✅ {len(results)} complaints found\n")
    for i, c in enumerate(results, 1):
        title = c.get("title") or c.get("description") or "N/A"
        date = c.get("date", "N/A")
        status = c.get("status", "N/A")
        print(f"  {i}. {title[:70]}")
        print(f"     📅 {date}  |  Status: {status}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
