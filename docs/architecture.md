# QuantAI Architecture

## Design goals

QuantAI separates quantitative research logic from transport, storage, and presentation concerns. Each analytical module should be usable from tests and notebooks without starting the web application.

## Implemented data flow

```text
yfinance
   |
   v
data loader -----> normalized market/fundamental data
   |                              |
   v                              v
risk metrics                 factor engine
   |                              |
   +--------------+---------------+
                  v
          portfolio optimizer
                  |
          +-------+----------------+----------------+
          v                        v                v
 efficient frontier     Monte Carlo simulation   walk-forward backtest
          |                        |                |
          +------------------------+----------------+
                  v
       FastAPI response schemas
                  |
                  v
        Next.js research dashboard
                  |
                  v
      constrained AI explanation
```

The machine-learning pipeline consumes point-in-time feature sets independently of the optimization pipeline. Its outputs are experimental evidence, not trading instructions.

## Module boundaries

- `app.quant`: pure or near-pure analytical logic with explicit inputs and outputs.
- `app.services`: orchestration across data, analytics, persistence, and explanations.
- `app.api`: validation and HTTP transport only; no financial formulas.
- `app.db`: persistence interfaces and implementations.
- `app.schemas`: stable typed contracts between backend and frontend.
- `frontend`: presentation and user interaction; calculations remain in the backend.

## Engineering principles

1. Prevent look-ahead bias with time-aware feature construction and validation.
2. Make financial assumptions explicit, including annualization factors and risk-free rates.
3. Keep vendor-specific data transformations inside the data layer.
4. Return structured results before generating human-readable explanations.
5. Treat AI-generated text as a constrained interpretation of computed evidence.
6. Test numerical edge cases, schema contracts, and representative integration paths.
7. Validate historical strategies with trailing-only estimation and auditable
   rebalance decisions rather than full-sample optimized weights.

## Initial persistence choice

SQLite is the planned default for the first release. Database access will remain isolated so PostgreSQL can be introduced without changing quantitative modules.

## Web application boundary

The implemented FastAPI layer mounts typed market, stock-analysis, and
portfolio endpoints under `/api/v1`. Route handlers perform HTTP validation and
error translation only; orchestration and short-lived caching live in
`app.services`, while all formulas remain in `app.quant`.

The Next.js App Router frontend consumes those contracts through a single API
client. TradingView Lightweight Charts owns OHLCV rendering, while Plotly owns
comparative and portfolio research charts. No financial metric is recalculated
in the browser.

The portfolio service requests the selected securities and SPY once, separates
the benchmark from the optimization universe, and passes normalized returns to
the backtest module. `app.quant.portfolio.backtest` owns rebalance scheduling,
trailing-window optimization, drifting positions, turnover costs, benchmark
alignment, downside and relative-risk diagnostics, rolling risk series,
performance statistics, and the audit log. The service only maps those domain
objects into response schemas; the frontend only renders them.

The robustness endpoint reuses the same cached normalized price frames but runs
independently from the primary portfolio response. The quantitative layer aligns
every parameter cell to one common evaluation start before rerunning the full
walk-forward engine. This keeps an expensive robustness study opt-in and avoids
mixing non-comparable sample periods in the heatmap.

Localization is intentionally split by responsibility. A typed frontend message
catalog translates navigation, controls, metrics, charts, assumptions, and
disclaimers, while the backend explanation route accepts `locale=en` or
`locale=zh-CN` for deterministic and optional OpenAI-generated research prose.
The language choice affects presentation only; model inputs and numerical outputs
remain identical across locales.

## Explanation boundary

`app.quant.explainability` converts a typed `StockAnalysisResponse` into a
compact evidence bundle. It assigns the disclosed volatility-based risk label
and prepares the metric interpretations and limitations before any model call.
Only the narrative summary and research observations may be authored by the
OpenAI model through a Pydantic Structured Outputs schema. The API key remains
server-side, response storage is disabled, and the endpoint falls back to a
deterministic narrative if OpenAI is not configured or unavailable.

## Historical market-data contract

`app.quant.data.load_stock_data` is the boundary between provider-specific data
and QuantAI research code. It currently uses `yfinance` with explicit daily-data
settings and returns:

- an ascending, duplicate-free, timezone-naive `DatetimeIndex` named `date`;
- raw `open`, `high`, `low`, and `close` values;
- a separate `adjusted_close` series for later return calculations;
- integer `volume` and a normalized uppercase `ticker` column.

The upstream downloader is injectable. Unit tests therefore validate the data
contract without relying on network availability or mutable vendor responses.
