# Dashboard and API

## Purpose

The QuantAI dashboard presents the completed research modules through a typed
FastAPI boundary and a responsive Next.js interface. Calculations remain in the
Python quantitative package; the browser only submits inputs and visualizes
structured results.

All pages carry a research-only disclaimer. The application does not label
historical model output as a live signal or investment recommendation.

## Backend

The FastAPI application entry point is `app.main:app`. Version-one endpoints
are mounted under `/api/v1`:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Service health and version |
| GET | `/market/overview` | One-year S&P 500, NASDAQ, VIX, and Bitcoin histories |
| GET | `/instruments/search?q={query}` | Cached global ticker/company discovery with local fallback |
| GET | `/stocks/{ticker}` | Price, risk, factor, fundamental, and saved ML evidence |
| GET | `/stocks/{ticker}/explanation?locale={en,zh-CN}` | Localized explanation of computed evidence |
| POST | `/portfolio/optimize` | Allocation, frontier, Monte Carlo, estimator diagnostics, and matched strategy baselines |
| POST | `/portfolio/robustness` | Common-period walk-forward parameter grid |

Pydantic models validate requests and responses and populate the generated
OpenAPI documentation. Only the local Next.js development origins are allowed
by CORS. Data-heavy GET results use a ten-minute in-memory cache to reduce
repeated provider calls. Standardized price downloads also use a range-aware
on-disk fallback cache. After a live provider failure, QuantAI selects the newest
cached history that starts no later than the requested window, trims it to the
requested dates, and never fills an earlier request from a shorter later-starting
cache. Stock responses expose cache time and last-observation metadata.
`QUANTAI_MARKET_DATA_CACHE_DIR` can override its default temporary-directory
location.

Stock and portfolio market-data failures use a structured `503` detail with the
code `market_data_unavailable` and the complete `unavailable_symbols` list. The
portfolio loader waits for every concurrent symbol request before reporting the
failure, so the dashboard can identify all missing assets or benchmarks in one
response instead of exposing only the first provider exception. Browser-level
connection failures are retried once and localized in English or Chinese.

Start the backend from the repository root:

```bash
python -m uvicorn app.main:app --app-dir backend --reload
```

OpenAPI documentation is available at `http://localhost:8000/docs`.

## Frontend

The frontend uses Next.js App Router, React, TypeScript, and Tailwind CSS v4.
TradingView Lightweight Charts renders the OHLCV price view; Plotly renders
cross-market comparisons, allocation, efficient frontier, Monte Carlo
percentile bands, historical wealth paths, and drawdown comparisons.

The visual language is designed for an academic portfolio rather than a trading
terminal: light report surfaces, a deep navy research sidebar, restrained teal
accents, serif analytical headings, and high-contrast metric cards. The layout
is responsive, with a compact mobile navigation pattern for narrow screens.

English and Simplified Chinese strings live in a typed frontend dictionary.
The selected locale is persisted in browser storage and is also passed to the
explanation endpoint, so both interface copy and generated research prose switch
together without changing any numerical calculation.

The three primary routes are:

- `/market-overview`: latest market snapshots, one-year sparklines, and
  normalized cross-asset paths;
- `/stock-analysis`: ticker search, OHLCV chart, risk metrics, current factor
  score, fundamentals, saved machine-learning comparison, and a labeled
  evidence-grounded explanation. A browser-local watchlist, shareable ticker
  state, price CSV export, and compact JSON research snapshot support repeated
  analysis;
- `/portfolio-optimizer`: portfolio constraints, optimal allocation,
  efficient frontier, one-year simulation distribution, and a configurable
  trailing-only walk-forward study against SPY. The interface rejects clearly
  infeasible weight caps before an API request, provides research-universe
  presets, stores model and backtest inputs in a shareable URL, visualizes
  wealth, drawdown, rolling volatility, and rolling beta paths, exposes
  downside and benchmark-relative diagnostics plus recent rebalance decisions,
  compares sample and OAS covariance estimators, and benchmarks maximum Sharpe
  against equal-weight and risk-parity allocations under matched assumptions,
  runs an optional common-period parameter-sensitivity heatmap, and exports
  allocation CSV, risk-enriched backtest CSV, robustness-grid CSV, and the full
  structured result.

Configure the backend URL when it differs from the default:

```bash
copy .env.example .env.local
```

Then run from `frontend/`:

```bash
pnpm install
pnpm dev
```

The default frontend address is `http://localhost:3000`.

## Verification

Backend contract tests use FastAPI's in-process test client and do not require
live network access. Frontend validation includes TypeScript checking, ESLint,
and a production build:

```bash
python -m pytest -q
cd frontend
pnpm typecheck
pnpm lint
pnpm build
```

On 30 September 2026, all three pages were also exercised end to end against a
live local API. The portfolio page returned the allocation, 10,000-path risk
simulation, and a 35-rebalance walk-forward history. The latter covered 3
January 2018 through 29 September 2026 using a 756-day lookback, 63-day
rebalance interval, and 10 bps modeled transaction cost. English and Chinese
desktop views and a 390-by-844 mobile viewport were checked with no browser
console warnings or errors.

The risk-diagnostics extension was subsequently exercised against the same live
response. Sortino, downside deviation, beta, correlation, tracking error,
information ratio, drawdown duration, and 63-day rolling series all returned
finite values after their required warm-up window.

## Limitations

- Yahoo Finance responses are not guaranteed, institutional, or real-time.
- The in-memory cache is process-local and intended only for this first version.
- Watchlists use browser storage and do not synchronize between devices.
- Shareable portfolio URLs preserve inputs but intentionally do not freeze
  vendor data or calculated results.
- Walk-forward output is hypothetical and remains sensitive to the selected
  surviving universe, lookback, rebalance schedule, cost input, and benchmark.
- Factor values are current snapshots; they are not point-in-time backtests.
- Saved ML metrics are historical holdout evidence, not current forecasts.
- OpenAI text generation requires a server-side API key; deterministic evidence
  summaries are used when it is not configured or the provider is unavailable.
- Production deployment would require authentication, rate limiting,
  persistent caching, observability, and a managed database.
