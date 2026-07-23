"""Cross-reference service: unifies data from ML, OLX, and Maps."""

from __future__ import annotations

import logging
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class CrossReferenceService:
    """Cross-references data from ML, OLX, and Maps for unified insights."""

    def __init__(self, similarity_threshold: float = 0.6) -> None:
        self._threshold = similarity_threshold

    # ------------------------------------------------------------------
    # Price comparison (ML new vs OLX used)
    # ------------------------------------------------------------------

    def compare_prices(
        self, ml_products: list[dict], olx_ads: list[dict]
    ) -> list[dict]:
        """Compare prices of similar products between ML (new) and OLX (used)."""
        comparisons: list[dict] = []

        for ml_item in ml_products:
            ml_title = ml_item.get("title", "")
            ml_price = ml_item.get("price")
            if not ml_price:
                continue

            best_match = None
            best_score = 0.0

            for olx_item in olx_ads:
                olx_title = olx_item.get("title", "")
                score = self._similarity(ml_title, olx_title)
                if score > best_score and score >= self._threshold:
                    best_score = score
                    best_match = olx_item

            if best_match and best_match.get("price"):
                olx_price = best_match["price"]
                savings = ml_price - olx_price
                savings_pct = (savings / ml_price * 100) if ml_price > 0 else 0

                comparisons.append({
                    "product": ml_title[:60],
                    "ml_price": round(ml_price, 2),
                    "olx_price": round(olx_price, 2),
                    "olx_title": best_match.get("title", "")[:60],
                    "savings": round(savings, 2),
                    "savings_pct": round(savings_pct, 1),
                    "match_confidence": round(best_score, 2),
                    "olx_location": best_match.get("location", ""),
                    "recommendation": self._price_recommendation(
                        ml_price, olx_price, savings_pct
                    ),
                })

        comparisons.sort(key=lambda x: x.get("savings", 0), reverse=True)
        return comparisons

    def _price_recommendation(
        self, new_price: float, used_price: float, savings_pct: float
    ) -> str:
        if savings_pct >= 50:
            return "Excelente economia! Usado vale muito a pena."
        elif savings_pct >= 30:
            return "Boa economia. Considere usado se estado for bom."
        elif savings_pct >= 15:
            return "Economia moderada. Novo pode valer pela garantia."
        return "Pouca diferença. Prefira novo pela garantia."

    # ------------------------------------------------------------------
    # Enriched leads (Maps + online presence)
    # ------------------------------------------------------------------

    def enrich_leads(
        self,
        maps_businesses: list[dict],
        ml_products: list[dict],
        olx_ads: list[dict],
    ) -> list[dict]:
        """Enrich Maps leads with online presence and trust score."""
        enriched = []

        for biz in maps_businesses:
            biz_name = biz.get("name", "")
            ml_presence = self._check_presence(biz_name, ml_products)
            olx_presence = self._check_presence(biz_name, olx_ads)
            score = self._trust_score(biz, ml_presence, olx_presence)

            enriched.append({
                **biz,
                "online_presence_ml": ml_presence,
                "online_presence_olx": olx_presence,
                "trust_score": score,
                "trust_level": self._trust_level(score),
                "insight": self._lead_insight(biz, ml_presence, olx_presence),
            })

        enriched.sort(key=lambda x: x.get("trust_score", 0), reverse=True)
        return enriched

    def _check_presence(self, name: str, items: list[dict]) -> bool:
        for item in items:
            title = item.get("title", "")
            if self._similarity(name, title) >= 0.5:
                return True
        return False

    def _trust_score(
        self, biz: dict, ml_presence: bool, olx_presence: bool
    ) -> float:
        score = 5.0
        rating = biz.get("rating")
        if rating:
            score += (rating - 3.0) * 1.5
        if ml_presence:
            score += 1.0
        if olx_presence:
            score += 0.5
        if biz.get("website"):
            score += 0.5
        if biz.get("phone"):
            score += 0.5
        reviews = biz.get("reviews_count")
        if reviews:
            if reviews > 50:
                score += 1.0
            elif reviews > 10:
                score += 0.5
        return round(max(0, min(10, score)), 1)

    def _trust_level(self, score: float) -> str:
        if score >= 8:
            return "Alto"
        elif score >= 6:
            return "Médio"
        elif score >= 4:
            return "Baixo"
        return "Muito Baixo"

    def _lead_insight(
        self, biz: dict, ml_presence: bool, olx_presence: bool
    ) -> str:
        parts = []
        if not biz.get("website"):
            parts.append("Website nao detectado no Maps (pode existir - verificar)")
        if not ml_presence and not olx_presence:
            parts.append("Sem presenca em marketplaces")
        if biz.get("rating"):
            if biz["rating"] >= 4.5:
                parts.append("Excelente reputacao local")
            elif biz["rating"] < 3.5:
                parts.append("Reputacao baixa")
        return " | ".join(parts) if parts else "Lead padrao"

    # ------------------------------------------------------------------
    # Global report
    # ------------------------------------------------------------------

    def generate_report(
        self,
        ml_data: list[dict],
        maps_data: list[dict],
        olx_data: list[dict],
    ) -> dict:
        """Generate a unified 360 report."""
        return {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "ml_products": len(ml_data),
                "maps_businesses": len(maps_data),
                "olx_ads": len(olx_data),
                "total_items": len(ml_data) + len(maps_data) + len(olx_data),
            },
            "price_comparisons": self.compare_prices(ml_data, olx_data),
            "enriched_leads": self.enrich_leads(maps_data, ml_data, olx_data),
            "insights": self._global_insights(ml_data, maps_data, olx_data),
        }

    def _global_insights(
        self,
        ml_data: list[dict],
        maps_data: list[dict],
        olx_data: list[dict],
    ) -> list[str]:
        insights: list[str] = []

        ml_prices = [p["price"] for p in ml_data if p.get("price")]
        olx_prices = [p["price"] for p in olx_data if p.get("price")]

        if ml_prices and olx_prices:
            ml_avg = sum(ml_prices) / len(ml_prices)
            olx_avg = sum(olx_prices) / len(olx_prices)
            diff = ((ml_avg - olx_avg) / ml_avg * 100) if ml_avg > 0 else 0
            insights.append(
                f"Preco medio ML R$ {ml_avg:.0f} novo vs OLX R$ {olx_avg:.0f} "
                f"usado - economia media de {diff:.0f}%"
            )

        if maps_data:
            high = [b for b in maps_data if b.get("rating") and b["rating"] >= 4.5]
            insights.append(f"{len(high)}/{len(maps_data)} empresas com rating >= 4.5")
            no_site = [b for b in maps_data if not b.get("website")]
            insights.append(f"{len(no_site)}/{len(maps_data)} SEM website")

        return insights

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
