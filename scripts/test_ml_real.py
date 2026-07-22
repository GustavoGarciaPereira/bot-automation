#!/usr/bin/env python3
"""Manual validation script — runs a real Mercado Livre search via Selenium.

Usage::

    python scripts/test_ml_real.py [--visible]

Without ``--visible`` the browser runs headless.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    headless = "--visible" not in sys.argv

    from src.plugins.mercado_livre.scraper import MercadoLivreScraper

    scraper = MercadoLivreScraper(headless=headless)
    query = "notebook dell"
    max_results = 5

    print(f"\n🔍 Searching Mercado Livre for: {query!r}")
    print(f"   Headless: {headless}")
    print()

    results = await scraper.search(query, max_results=max_results)

    if not results:
        print("❌ No products found.")
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
