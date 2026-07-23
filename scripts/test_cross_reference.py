#!/usr/bin/env python3
"""Manual validation — Cross-Reference 360 (ML + OLX + Maps)."""

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

    parser = argparse.ArgumentParser(description="Cross-Reference 360")
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    from src.plugins.mercado_livre.scraper import MercadoLivreScraper
    from src.plugins.google_maps.scraper import GoogleMapsScraper
    from src.plugins.olx.scraper import OLXScraper
    from src.services.cross_reference import CrossReferenceService
    from src.services.cross_report import CrossReportExporter

    print("\n🔗 Cross-Reference 360 — Coletando dados das 3 plataformas...\n")

    headless = not args.visible

    # 1. ML
    print("🛒 Mercado Livre (notebook dell)...")
    ml = MercadoLivreScraper(headless=headless)
    ml_data = await ml.search("notebook dell", max_results=5)
    print(f"   ✅ {len(ml_data)} produtos\n")

    # 2. OLX
    print("📦 OLX (notebook dell)...")
    olx = OLXScraper(headless=headless)
    olx_data = await olx.search("notebook dell", max_results=10)
    print(f"   ✅ {len(olx_data)} anuncios\n")

    # 3. Maps
    print("🗺 Google Maps (lojas de informatica em campinas sp)...")
    maps = GoogleMapsScraper(headless=headless)
    maps_data = await maps.search("lojas de informatica em campinas sp", max_results=10)
    print(f"   ✅ {len(maps_data)} empresas\n")

    # 4. Cross
    print("🔗 Cruzando dados...")
    cross = CrossReferenceService()
    report = cross.generate_report(ml_data, maps_data, olx_data)

    # 5. Print
    print(f"\n{'='*60}")
    print("📊 RELATORIO 360")
    print(f"{'='*60}")
    s = report["summary"]
    print(f"   ML: {s['ml_products']}  |  Maps: {s['maps_businesses']}  |  OLX: {s['olx_ads']}  |  Total: {s['total_items']}")

    print(f"\n📈 COMPARACAO DE PRECOS (ML novo vs OLX usado):")
    for comp in report.get("price_comparisons", [])[:5]:
        print(f"\n   {comp['product'][:50]}")
        print(f"   ML: R$ {comp['ml_price']:.0f}  |  OLX: R$ {comp['olx_price']:.0f}")
        print(f"   Economia: R$ {comp['savings']:.0f} ({comp['savings_pct']:.0f}%)")
        print(f"   {comp['recommendation']}")

    print(f"\n🎯 LEADS ENRIQUECIDOS (top 5):")
    for lead in report.get("enriched_leads", [])[:5]:
        print(f"\n   {lead.get('name', '?')[:50]}")
        print(f"   Rating: {lead.get('rating', 'N/A')}  |  Score: {lead.get('trust_score', 0)}/10  |  {lead.get('trust_level', '?')}")
        print(f"   Insight: {lead.get('insight', '')}")

    print(f"\n💡 INSIGHTS:")
    for ins in report.get("insights", []):
        print(f"   {ins}")

    # 6. Export
    exporter = CrossReportExporter()
    fp = exporter.export(report)
    if fp:
        print(f"\n📁 Relatorio salvo: {fp}")

    print("\n✅ Cross-Reference completo!\n")


if __name__ == "__main__":
    asyncio.run(main())
