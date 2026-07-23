#!/usr/bin/env python3
"""Manual validation script — fetches Reclame Aqui complaints via cloudscraper.

Usage::

    python scripts/test_ra_real.py
    python scripts/test_ra_real.py --company "Magazine Luiza"
    python scripts/test_ra_real.py --company nubank --pages 3
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
    args = parser.parse_args()

    from src.plugins.reclame_aqui.scraper import ReclameAquiScraper, _clear_config_cache, slugify

    _clear_config_cache()

    scraper = ReclameAquiScraper()
    slug = slugify(args.company)

    print(f"\n🔍 Fetching Reclame Aqui for: {slug!r} (max {args.pages} pages)")
    print()

    results = await scraper.search(slug, max_pages=args.pages)

    if not results:
        print("❌ No complaints found (or CloudFlare blocked).")
        sys.exit(1)

    print(f"✅ {len(results)} complaints found\n")
    for i, c in enumerate(results, 1):
        title = c.get("title", "?")[:70]
        date = c.get("date", "N/A")
        status = c.get("status", "N/A")
        rating = c.get("rating", "N/A")
        print(f"  {i}. {title}")
        print(f"     📅 {date}  |  Status: {status}  |  ⭐ {rating}")
        if c.get("text"):
            print(f"     📝 {c['text'][:100]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
