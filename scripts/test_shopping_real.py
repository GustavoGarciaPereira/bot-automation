#!/usr/bin/env python3
"""Manual validation — Google Shopping scraper.

Usage::

    python scripts/test_shopping_real.py --visible
    python scripts/test_shopping_real.py --query "iphone 15" --visible
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

    parser = argparse.ArgumentParser(description="Test Google Shopping scraper")
    parser.add_argument("--query", default="notebook dell")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    from src.plugins.google_shopping.scraper import GoogleShoppingScraper, _clear_config_cache

    _clear_config_cache()
    scraper = GoogleShoppingScraper(headless=not args.visible)

    print(f"\n🔍 Google Shopping: '{args.query}'  |  Max: {args.max}")
    print()

    results = await scraper.search(args.query, max_results=args.max)

    if not results:
        print("❌ No products found.")
        sys.exit(1)

    print(f"✅ {len(results)} products found\n")
    for i, p in enumerate(results, 1):
        title = p.get("title", "?")[:60]
        price = p.get("price", "N/A")
        store = p.get("store_name", "N/A")
        rating = p.get("rating", "N/A")
        print(f"  {i}. {title}")
        print(f"     💰 R$ {price}  |  Loja: {store}  |  ⭐ {rating}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
