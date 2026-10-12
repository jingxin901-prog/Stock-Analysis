"""Version-one dashboard endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.quant.data import MarketDataError
from app.schemas import (
    HealthResponse,
    InstrumentSearchResponse,
    MarketOverviewResponse,
    PortfolioRequest,
    PortfolioResponse,
    PortfolioRobustnessRequest,
    PortfolioRobustnessResponse,
    StockAnalysisResponse,
    StockExplanationResponse,
)
from app.services import (
    PortfolioMarketDataUnavailableError,
    analyze_portfolio_robustness,
    get_market_overview,
    get_stock_analysis,
    get_stock_explanation,
    optimize_portfolio,
    search_instrument_catalog,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="quantai-api", version="0.1.0")


@router.get(
    "/market/overview",
    response_model=MarketOverviewResponse,
    tags=["market"],
)
def market_overview() -> MarketOverviewResponse:
    try:
        return get_market_overview()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get(
    "/instruments/search",
    response_model=InstrumentSearchResponse,
    tags=["market"],
)
def instrument_search(
    q: str = Query(min_length=2, max_length=64),
    limit: int = Query(default=8, ge=1, le=20),
) -> InstrumentSearchResponse:
    try:
        return search_instrument_catalog(q, limit=limit)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/stocks/{ticker}",
    response_model=StockAnalysisResponse,
    tags=["stocks"],
)
def stock_analysis(
    ticker: str,
    start: str = Query(default="2015-01-01", description="Inclusive ISO start date"),
    peers: str | None = Query(
        default=None,
        max_length=256,
        description="Optional comma- or pipe-delimited custom factor peers",
    ),
) -> StockAnalysisResponse:
    try:
        return get_stock_analysis(ticker, start=start, peer_tickers=_parse_peer_query(peers))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except MarketDataError as exc:
        raise _market_data_http_exception([ticker], str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get(
    "/stocks/{ticker}/explanation",
    response_model=StockExplanationResponse,
    tags=["explainability"],
)
def stock_explanation(
    ticker: str,
    start: str = Query(default="2015-01-01", description="Inclusive ISO start date"),
    locale: Literal["en", "zh-CN"] = Query(default="en"),
    peers: str | None = Query(default=None, max_length=256),
) -> StockExplanationResponse:
    try:
        return get_stock_explanation(
            ticker,
            start=start,
            locale=locale,
            peer_tickers=_parse_peer_query(peers),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except MarketDataError as exc:
        raise _market_data_http_exception([ticker], str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _parse_peer_query(peers: str | None) -> list[str] | None:
    if peers is None:
        return None
    return [value.strip() for value in peers.replace(",", "|").split("|") if value.strip()]


@router.post(
    "/portfolio/optimize",
    response_model=PortfolioResponse,
    tags=["portfolio"],
)
def portfolio_optimization(request: PortfolioRequest) -> PortfolioResponse:
    try:
        return optimize_portfolio(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PortfolioMarketDataUnavailableError as exc:
        raise _market_data_http_exception(exc.unavailable_symbols, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post(
    "/portfolio/robustness",
    response_model=PortfolioRobustnessResponse,
    tags=["portfolio"],
)
def portfolio_robustness(
    request: PortfolioRobustnessRequest,
) -> PortfolioRobustnessResponse:
    try:
        return analyze_portfolio_robustness(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PortfolioMarketDataUnavailableError as exc:
        raise _market_data_http_exception(exc.unavailable_symbols, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _market_data_http_exception(
    unavailable_symbols: list[str] | tuple[str, ...],
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "market_data_unavailable",
            "message": message,
            "unavailable_symbols": list(unavailable_symbols),
        },
    )
