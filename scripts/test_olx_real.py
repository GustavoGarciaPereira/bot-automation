#!/usr/bin/env python3
"""Manual validation — OLX Brasil scraper (single session).

Usage::
    python scripts/test_olx_real.py --visible
    python scripts/test_olx_real.py --visible --debug
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

    parser = argparse.ArgumentParser(description="Test OLX scraper")
    parser.add_argument("--query", default="notebook dell")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--debug", action="store_true",
                        help="Save HTML + samples during scraping (same session)")
    args = parser.parse_args()

    from src.plugins.olx.scraper import OLXScraper, _clear_config_cache
    _clear_config_cache()

    scraper = OLXScraper(headless=not args.visible)

    print(f"\n🔍 OLX: '{args.query}'  |  Max: {args.max}")
    print(f"   Headless: {not args.visible}  |  Debug: {args.debug}")
    print()

    results = await scraper.search(args.query, max_results=args.max, save_debug=args.debug)

    if not results:
        print("❌ No ads found.")
        sys.exit(1)

    print(f"✅ {len(results)} ads found\n")
    for i, a in enumerate(results, 1):
        title = a.get("title", "?")[:60]
        price = a.get("price", "N/A")
        loc = a.get("location", "N/A")
        date = a.get("date", "N/A")
        print(f"  {i}. {title}")
        print(f"     💰 R$ {price}  |  📍 {loc}  |  📅 {date}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
