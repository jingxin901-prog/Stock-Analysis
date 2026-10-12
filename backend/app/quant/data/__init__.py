"""Market and fundamental data access."""

from .data_loader import (
    DEFAULT_START_DATE,
    STANDARD_COLUMNS,
    EmptyMarketDataError,
    MarketDataDependencyError,
    MarketDataDownloadError,
    MarketDataError,
    MarketDataSchemaError,
    load_stock_data,
    normalize_ticker,
)
from .fundamental_loader import (
    EmptyFundamentalDataError,
    FundamentalDataDependencyError,
    FundamentalDataDownloadError,
    FundamentalDataError,
    FundamentalSnapshot,
    load_fundamental_data,
)
from .instrument_context import (
    CHINA_A_FACTOR_UNIVERSE,
    HONG_KONG_FACTOR_UNIVERSE,
    US_FACTOR_UNIVERSE,
    InstrumentContext,
    get_instrument_context,
    infer_portfolio_benchmark,
    portfolio_quote_currencies,
)
from .instrument_search import InstrumentSearchRecord, search_instruments
from .peer_selection import (
    PEER_CATALOG,
    FactorPeerSelection,
    PeerCandidate,
    classify_market_cap,
    normalize_sector,
    select_factor_peers,
)

__all__ = [
    "DEFAULT_START_DATE",
    "STANDARD_COLUMNS",
    "EmptyMarketDataError",
    "MarketDataDependencyError",
    "MarketDataDownloadError",
    "MarketDataError",
    "MarketDataSchemaError",
    "EmptyFundamentalDataError",
    "FundamentalDataDependencyError",
    "FundamentalDataDownloadError",
    "FundamentalDataError",
    "FundamentalSnapshot",
    "InstrumentContext",
    "InstrumentSearchRecord",
    "FactorPeerSelection",
    "PeerCandidate",
    "PEER_CATALOG",
    "CHINA_A_FACTOR_UNIVERSE",
    "HONG_KONG_FACTOR_UNIVERSE",
    "US_FACTOR_UNIVERSE",
    "get_instrument_context",
    "infer_portfolio_benchmark",
    "classify_market_cap",
    "load_fundamental_data",
    "load_stock_data",
    "normalize_ticker",
    "normalize_sector",
    "portfolio_quote_currencies",
    "search_instruments",
    "select_factor_peers",
]
