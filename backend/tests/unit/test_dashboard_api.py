"""HTTP contract tests for the FastAPI dashboard layer."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.api.v1.routes.dashboard import _parse_peer_query
from app.main import app, create_app
from app.schemas.dashboard import (
    IndexPoint,
    InstrumentSearchResponse,
    InstrumentSearchResultResponse,
    MarketInstrument,
    MarketOverviewResponse,
    PortfolioRequest,
    PortfolioRobustnessRequest,
    StockExplanationResponse,
)
from app.services import PortfolioMarketDataUnavailableError
from fastapi.testclient import TestClient


class DashboardApiTests(unittest.TestCase):
    def test_custom_peer_query_accepts_commas_and_pipes(self) -> None:
        self.assertEqual(
            _parse_peer_query("AAPL, MSFT|GOOGL"),
            ["AAPL", "MSFT", "GOOGL"],
        )

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_and_openapi_are_available(self) -> None:
        health = self.client.get("/api/v1/health")
        schema = self.client.get("/openapi.json")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/api/v1/portfolio/optimize", schema.json()["paths"])
        self.assertIn("/api/v1/portfolio/robustness", schema.json()["paths"])
        self.assertIn("/api/v1/stocks/{ticker}/explanation", schema.json()["paths"])
        self.assertIn("/api/v1/instruments/search", schema.json()["paths"])

    def test_local_frontend_origin_receives_cors_header(self) -> None:
        response = self.client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})

        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")

    def test_public_frontend_origin_can_be_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"QUANTAI_CORS_ORIGINS": "https://quantai.vercel.app/"},
        ):
            client = TestClient(create_app())

        response = client.get(
            "/api/v1/health",
            headers={"Origin": "https://quantai.vercel.app"},
        )

        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://quantai.vercel.app",
        )

    @patch("app.api.v1.routes.dashboard.get_market_overview")
    def test_market_route_uses_typed_response(self, mocked_service: object) -> None:
        mocked_service.return_value = MarketOverviewResponse(  # type: ignore[attr-defined]
            instruments=[
                MarketInstrument(
                    key="sp500",
                    name="S&P 500",
                    symbol="^GSPC",
                    latest_price=6_000.0,
                    change=12.0,
                    change_percent=0.002,
                    as_of="2026-09-28",
                    history=[IndexPoint(date="2026-09-28", value=6_000.0)],
                )
            ],
            source="test",
        )

        response = self.client.get("/api/v1/market/overview")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["instruments"][0]["symbol"], "^GSPC")

    @patch("app.api.v1.routes.dashboard.search_instrument_catalog")
    def test_instrument_search_route_uses_typed_response(self, mocked_service: object) -> None:
        mocked_service.return_value = InstrumentSearchResponse(  # type: ignore[attr-defined]
            query="贵州茅台",
            results=[
                InstrumentSearchResultResponse(
                    symbol="600519.SS",
                    name="贵州茅台 / Kweichow Moutai",
                    exchange="Shanghai",
                    quote_type="Equity",
                    market="china_a",
                    currency="CNY",
                )
            ],
            source="local",
        )

        response = self.client.get("/api/v1/instruments/search", params={"q": "贵州茅台"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["symbol"], "600519.SS")

    def test_duplicate_portfolio_tickers_are_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/portfolio/optimize",
            json={"tickers": ["AAPL", "aapl"]},
        )

        self.assertEqual(response.status_code, 422)

    @patch("app.api.v1.routes.dashboard.optimize_portfolio")
    def test_portfolio_data_failure_returns_structured_symbols(
        self,
        mocked_service: object,
    ) -> None:
        mocked_service.side_effect = PortfolioMarketDataUnavailableError(  # type: ignore[attr-defined]
            ["NVDA", "SPY"],
            asset_symbols=["NVDA"],
            benchmark_symbol="SPY",
        )

        response = self.client.post(
            "/api/v1/portfolio/optimize",
            json={"tickers": ["AAPL", "NVDA"]},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "market_data_unavailable")
        self.assertEqual(response.json()["detail"]["unavailable_symbols"], ["NVDA", "SPY"])

    @patch("app.api.v1.routes.dashboard.get_stock_explanation")
    def test_explanation_route_discloses_deterministic_mode(self, mocked_service: object) -> None:
        mocked_service.return_value = StockExplanationResponse(  # type: ignore[attr-defined]
            ticker="NVDA",
            summary="A deterministic research summary grounded in computed evidence.",
            risk_level="Elevated",
            observations=["Historical volatility is elevated."],
            evidence=[],
            limitations=["Historical measurements do not forecast future returns."],
            source="deterministic",
            model=None,
            provider_message="OPENAI_API_KEY is not configured.",
            generated_at_utc="2026-09-29T00:00:00+00:00",
        )

        response = self.client.get("/api/v1/stocks/NVDA/explanation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "deterministic")

    def test_request_schema_normalizes_tickers(self) -> None:
        request = PortfolioRequest(
            tickers=[" aapl ", "msft"], benchmark=" spy ", base_currency="USD"
        )

        self.assertEqual(request.tickers, ["AAPL", "MSFT"])
        self.assertEqual(request.benchmark, "SPY")

    def test_robustness_schema_sorts_parameter_grid(self) -> None:
        request = PortfolioRobustnessRequest(
            tickers=["msft", "aapl"],
            lookback_options=[756, 252, 504],
            rebalance_options=[126, 21, 63],
        )

        self.assertEqual(request.tickers, ["MSFT", "AAPL"])
        self.assertEqual(request.lookback_options, [252, 504, 756])
        self.assertEqual(request.rebalance_options, [21, 63, 126])


if __name__ == "__main__":
    unittest.main()
