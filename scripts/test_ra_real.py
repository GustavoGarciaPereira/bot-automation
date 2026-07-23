#!/usr/bin/env python3
"""Manual validation script — runs a real Reclame Aqui search.

Usage::

    python scripts/test_ra_real.py --visible
    python scripts/test_ra_real.py --visible --company "Magazine Luiza"
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
    parser.add_argument("--company", default="magazine-luiza")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    from src.plugins.reclame_aqui.scraper import ReclameAquiScraper, _clear_config_cache

    _clear_config_cache()

    scraper = ReclameAquiScraper(headless=not args.visible)

    print(f"\n🔍 Scraping Reclame Aqui for: {args.company!r}")
    print(f"   Headless: {not args.visible}  |  Max pages: {args.pages}")
    print()

    results = await scraper.search(args.company, max_pages=args.pages)

    if not results:
        print("❌ No complaints found.")
        sys.exit(1)

    print(f"✅ {len(results)} complaints found\n")
    for i, c in enumerate(results, 1):
        title = c.get("title", "?")[:70]
        date = c.get("date", "N/A")
        status = c.get("status", "N/A")
        url = c.get("complaint_url", "")[:80]
        print(f"  {i}. {title}")
        print(f"     📅 {date}  |  Status: {status}")
        if c.get("text"):
            print(f"     📝 {c['text'][:100]}...")
        if url:
            print(f"     🔗 {url}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
