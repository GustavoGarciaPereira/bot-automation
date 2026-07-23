#!/usr/bin/env python3
"""Manual validation — OLX Brasil scraper.

Usage::
    python scripts/test_olx_real.py --visible
    python scripts/test_olx_real.py --query "iphone 15" --visible
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
    args = parser.parse_args()

    from src.plugins.olx.scraper import OLXScraper, _clear_config_cache
    _clear_config_cache()
    scraper = OLXScraper(headless=not args.visible)

    print(f"\n🔍 OLX: '{args.query}'  |  Max: {args.max}\n")
    results = await scraper.search(args.query, max_results=args.max)

    if not results:
        print("❌ No ads found.")
        sys.exit(1)

    print(f"✅ {len(results)} ads found\n")
    for i, a in enumerate(results, 1):
        print(f"  {i}. {a.get('title', '?')[:60]}")
        print(f"     💰 R$ {a.get('price', 'N/A')}  |  📍 {a.get('location', 'N/A')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
