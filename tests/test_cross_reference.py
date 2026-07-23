"""Tests for Cross-Reference service."""

from __future__ import annotations

from src.services.cross_reference import CrossReferenceService


def _service() -> CrossReferenceService:
    return CrossReferenceService()


class TestComparePrices:
    def test_match_found(self) -> None:
        svc = _service()
        ml = [{"title": "Notebook Dell Inspiron", "price": 5000.0}]
        olx = [{"title": "Notebook Dell Inspiron usado", "price": 3000.0}]
        result = svc.compare_prices(ml, olx)
        assert len(result) == 1
        assert result[0]["savings"] == 2000.0
        assert result[0]["savings_pct"] == 40.0

    def test_no_match(self) -> None:
        svc = _service()
        ml = [{"title": "Notebook Dell", "price": 5000.0}]
        olx = [{"title": "iPhone 15", "price": 3000.0}]
        result = svc.compare_prices(ml, olx)
        assert len(result) == 0

    def test_empty_data(self) -> None:
        svc = _service()
        assert svc.compare_prices([], []) == []
        assert svc.compare_prices([{"title": "A", "price": 10}], []) == []


class TestTrustScore:
    def test_high_score(self) -> None:
        svc = _service()
        biz = {"name": "Loja A", "rating": 4.9, "website": "x.com", "phone": "123"}
        score = svc._trust_score(biz, ml_presence=True, olx_presence=True)
        assert score >= 8.0

    def test_low_score(self) -> None:
        svc = _service()
        biz = {"name": "Loja B", "rating": 2.0, "website": None, "phone": None}
        score = svc._trust_score(biz, ml_presence=False, olx_presence=False)
        assert score < 4.0


class TestEnrichLeads:
    def test_enriches_all(self) -> None:
        svc = _service()
        biz = [{"name": "Loja X", "rating": 4.5}]
        result = svc.enrich_leads(biz, [], [])
        assert len(result) == 1
        assert "trust_score" in result[0]
        assert "insight" in result[0]

    def test_online_presence(self) -> None:
        svc = _service()
        biz = [{"name": "Notebook Shop"}]
        ml = [{"title": "Notebook Shop - notebook usado"}]
        result = svc.enrich_leads(biz, ml, [])
        assert result[0]["online_presence_ml"] is True


class TestGlobalInsights:
    def test_price_insight(self) -> None:
        svc = _service()
        ml = [{"title": "A", "price": 100}, {"title": "B", "price": 200}]
        olx = [{"title": "A", "price": 50}, {"title": "B", "price": 100}]
        maps = []
        insights = svc._global_insights(ml, maps, olx)
        assert any("Preco medio" in i for i in insights)

    def test_empty_returns_empty(self) -> None:
        svc = _service()
        assert svc._global_insights([], [], []) == []


class TestSimilarity:
    def test_similar(self) -> None:
        svc = _service()
        assert svc._similarity("Notebook Dell", "Notebook Dell") > 0.9

    def test_different(self) -> None:
        svc = _service()
        assert svc._similarity("Notebook Dell", "iPhone 15") < 0.3

    def test_empty(self) -> None:
        svc = _service()
        assert svc._similarity("", "A") == 0.0
        assert svc._similarity("A", "") == 0.0


class TestRecommendation:
    def test_50pct(self) -> None:
        svc = _service()
        r = svc._price_recommendation(100, 50, 50)
        assert "Excelente" in r

    def test_10pct(self) -> None:
        svc = _service()
        r = svc._price_recommendation(100, 90, 10)
        assert "Pouca" in r


class TestGenerateReport:
    def test_report_structure(self) -> None:
        svc = _service()
        report = svc.generate_report(
            [{"title": "A", "price": 100}],
            [{"name": "B"}],
            [{"title": "C", "price": 80}],
        )
        assert "summary" in report
        assert "price_comparisons" in report
        assert "enriched_leads" in report
        assert "insights" in report
        assert report["summary"]["total_items"] == 3
