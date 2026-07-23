#!/usr/bin/env python3
"""Manual validation script — runs real Reclame Aqui scraping via Selenium.

Usage::

    python scripts/test_ra_real.py --visible
    python scripts/test_ra_real.py --company "Magazine Luiza" --visible
    python scripts/test_ra_real.py --company nubank --visible --debug
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

    parser = argparse.ArgumentParser(description="Test Reclame Aqui scraper")
    parser.add_argument("--company", default="magazine-luiza-loja-online")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    from src.plugins.reclame_aqui.scraper import ReclameAquiScraper, _clear_config_cache, slugify

    _clear_config_cache()
    slug = slugify(args.company)

    scraper = ReclameAquiScraper(headless=not args.visible)

    print(f"\n🔍 Scraping Reclame Aqui for: {slug!r} (max {args.pages} pages)")
    print(f"   Headless: {not args.visible}  |  Debug: {args.debug}")
    print()

    results = await scraper.search(slug, max_pages=args.pages)

    if not results:
        print("❌ No complaints found.")
        print("   If RA blocked Selenium, try --visible to see what loads.")
        sys.exit(1)

    print(f"✅ {len(results)} complaints found\n")
    for i, c in enumerate(results, 1):
        print(f"  {i}. {c.get('title', '?')[:70]}")
        print(f"     📅 {c.get('date', 'N/A')}  |  {c.get('status', 'N/A')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
