#!/usr/bin/env python3
"""Manual validation script — runs a real Google Maps search via Selenium.

Usage::

    python scripts/test_maps_real.py                       # headless
    python scripts/test_maps_real.py --visible              # visible browser
    python scripts/test_maps_real.py --query "pizzaria"     # custom query
    python scripts/test_maps_real.py --max 5                # fewer results
    python scripts/test_maps_real.py --visible --debug      # visible + debug
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

    parser = argparse.ArgumentParser(description="Test Google Maps scraper")
    parser.add_argument("--query", default="dentistas em campinas sp")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    from src.plugins.google_maps.scraper import GoogleMapsScraper, _clear_config_cache

    _clear_config_cache()

    scraper = GoogleMapsScraper(headless=not args.visible)

    print(f"\n🔍 Searching Google Maps for: {args.query!r}")
    print(f"   Headless: {not args.visible}  |  Max: {args.max}")
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
