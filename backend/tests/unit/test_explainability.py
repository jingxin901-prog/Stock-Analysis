"""Tests for evidence-grounded AI explanations and deterministic fallback."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.quant.explainability.stock_explainer import (
    NarrativeDraft,
    generate_stock_explanation,
)
from app.schemas.dashboard import (
    FactorScoreResponse,
    FundamentalSnapshotResponse,
    InstrumentContextResponse,
    MarketDataStatusResponse,
    MLExperimentResponse,
    RiskMetricsResponse,
    StockAnalysisResponse,
)


def _analysis() -> StockAnalysisResponse:
    return StockAnalysisResponse(
        ticker="NVDA",
        source="test",
        instrument=InstrumentContextResponse(
            market="us", currency="USD", suggested_benchmark="SPY"
        ),
        data_status=MarketDataStatusResponse(
            provider="test",
            served_from_cache=False,
            last_observation="2026-09-28",
        ),
        prices=[],
        risk=RiskMetricsResponse(
            annualized_return=0.35,
            annualized_volatility=0.48,
            sharpe_ratio=0.73,
            maximum_drawdown=-0.42,
            value_at_risk=0.041,
            var_confidence_level=0.95,
            start_date="2015-01-02",
            end_date="2026-09-28",
            observations=2_951,
        ),
        fundamentals=FundamentalSnapshotResponse(
            pe_ratio=40.0,
            pb_ratio=25.0,
            ev_to_ebitda=32.0,
            roe=0.80,
            profit_margin=0.55,
            debt_ratio=0.20,
            retrieved_at_utc="2026-09-29T00:00:00+00:00",
        ),
        factor_score=FactorScoreResponse(
            value=33.3,
            momentum=66.7,
            quality=93.3,
            total=64.4,
            rank=2,
            universe_size=6,
            data_coverage=1.0,
            universe=["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL"],
        ),
        ml_experiment=MLExperimentResponse(
            status="available",
            ticker="NVDA",
            message="Historical holdout only.",
        ),
        disclaimer="Research only.",
    )


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            output_parsed=NarrativeDraft(
                summary="The supplied metrics show a mixed factor profile and elevated risk.",
                observations=[
                    "Quality is the strongest relative component.",
                    "Historical volatility is elevated under the stated heuristic.",
                ],
            )
        )


class ExplainabilityTests(unittest.TestCase):
    def test_missing_key_uses_deterministic_evidence(self) -> None:
        result = generate_stock_explanation(_analysis(), api_key="")

        self.assertEqual(result.source, "deterministic")
        self.assertEqual(result.risk_level, "Elevated")
        self.assertEqual(len(result.evidence), 4)
        self.assertIn("not configured", result.provider_message)
        self.assertIn("not provide investment advice", result.disclaimer)

    def test_openai_boundary_uses_structured_output_and_no_storage(self) -> None:
        responses = _FakeResponses()
        client = SimpleNamespace(responses=responses)

        result = generate_stock_explanation(_analysis(), client=client, model="test-model")

        self.assertEqual(result.source, "openai")
        self.assertEqual(result.model, "test-model")
        self.assertIs(responses.kwargs["text_format"], NarrativeDraft)
        self.assertFalse(responses.kwargs["store"])
        self.assertNotIn("buy", result.summary.lower())

    def test_chinese_locale_localizes_deterministic_explanation(self) -> None:
        result = generate_stock_explanation(_analysis(), api_key="", locale="zh-CN")

        self.assertEqual(result.source, "deterministic")
        self.assertIn("历史年化收益率", result.summary)
        self.assertEqual(result.evidence[0].label, "因子特征")
        self.assertIn("不构成投资建议", result.disclaimer)

    def test_provider_failure_falls_back_without_exposing_exception(self) -> None:
        class FailingResponses:
            def parse(self, **_: object) -> None:
                raise RuntimeError("secret provider detail")

        result = generate_stock_explanation(
            _analysis(), client=SimpleNamespace(responses=FailingResponses())
        )

        self.assertEqual(result.source, "deterministic")
        self.assertNotIn("secret provider detail", result.provider_message)


if __name__ == "__main__":
    unittest.main()
