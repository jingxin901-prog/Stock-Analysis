# QuantAI

**QuantAI: An Explainable AI-Powered Portfolio Optimization and Risk Analysis Platform**

QuantAI is a research-oriented quantitative finance platform designed to demonstrate an end-to-end workflow:

`market data -> financial metrics -> factor analysis -> portfolio optimization -> risk simulation -> machine-learning experiments -> explainable dashboard`

The project is intended for academic and portfolio demonstration. It does not provide investment advice and does not claim that financial markets can be predicted reliably.

## Current status

| Step | Scope | Status |
| --- | --- | --- |
| 1 | Engineering scaffold | Complete |
| 2 | Historical market-data loader | Complete |
| 3 | Live market-data validation | Complete |
| 4 | Return and risk metrics | Complete |
| 5 | Factor model | Complete |
| 6 | Portfolio optimization, simulation, and walk-forward validation | Complete |
| 7 | Machine-learning experiments | Complete |
| 8 | FastAPI and Next.js dashboard | Complete |
| 9 | Evidence-grounded AI research summaries | Complete |
| Later | Persistence and deployment hardening | Future |

## Repository layout

```text
quantai/
|-- backend/                 FastAPI and quantitative research package
|   |-- app/
|   |   |-- api/             Versioned HTTP routes
|   |   |-- core/            Configuration, logging, shared settings
|   |   |-- db/              Database session and persistence layer
|   |   |-- quant/           Quantitative research modules
|   |   |   |-- data/        Market and fundamental data access
|   |   |   |-- metrics/     Return and risk metrics
|   |   |   |-- factors/     Value, momentum, and quality factors
|   |   |   |-- portfolio/   Optimization, efficient frontier, and backtesting
|   |   |   |-- simulation/  Monte Carlo risk simulation
|   |   |   |-- ml/          Feature engineering and ML experiments
|   |   |   `-- explainability/ LLM-based result interpretation
|   |   |-- schemas/         API request/response models
|   |   `-- services/        Application orchestration
|   `-- tests/               Unit and integration tests
|-- frontend/                Next.js, React, Tailwind, and charting UI
|-- data/                    Local raw/interim/processed data (not committed)
|-- artifacts/               Generated models and reports (not committed)
|-- notebooks/               Exploratory research notebooks
|-- configs/                 Reproducible experiment configuration
|-- docs/                    Architecture and technical documentation
|-- scripts/                 Developer utilities
`-- research_report.md       Living academic-style research report
```

See [docs/architecture.md](docs/architecture.md) for module boundaries and the planned data flow.

## Development setup

QuantAI currently targets Python 3.11-3.13. Create an isolated environment and
install the project from the repository root:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows, activate it with `.venv\Scripts\activate`; on macOS or Linux, use
`source .venv/bin/activate`.

## Historical market data

The Phase 2 loader retrieves unadjusted daily OHLCV data from Yahoo Finance via
`yfinance`, while retaining adjusted close as a separate field:

```python
from app.quant.data import load_stock_data

prices = load_stock_data("NVDA")
print(prices.tail())
```

The default start date is `2015-01-01`. An explicitly supplied `end` date is
exclusive, matching `yfinance` semantics. The standardized result has a
duplicate-free `DatetimeIndex` named `date` and these columns:

```text
ticker, open, high, low, close, adjusted_close, volume
```

Successful live downloads are also written to a range-aware CSV cache outside
the repository. If a later Yahoo Finance request fails, the loader can reuse the
newest standardized snapshot whose date range covers the request and trims it to
the requested window. This lets rolling one-year dashboard queries survive a
provider interruption after their start date advances. API responses disclose
whether the cache was used, when it was saved, and its latest observation date. Set
`QUANTAI_MARKET_DATA_CACHE_DIR` to choose the cache location; otherwise QuantAI
uses the operating-system temporary directory. Cached observations are never
described as live prices.

Useful live fundamental snapshots are likewise stored atomically outside the
repository. If a subsequent provider request fails, QuantAI may use the last
successful snapshot with `source: fundamental-cache`; the factor response marks
`current_snapshot: false`, and the dashboard displays a stale-snapshot notice.
Set `QUANTAI_FUNDAMENTAL_CACHE_DIR` to choose its location. Cache fallback is a
continuity feature, not a substitute for point-in-time fundamental data.

The web research flow accepts any supported Yahoo Finance symbol, not only the
sample US names. Examples include `600519.SS` for Shanghai, `000858.SZ` for
Shenzhen, and `0700.HK` for Hong Kong. A cached search endpoint resolves ticker
codes and English or Chinese company names through Yahoo Finance, with local
aliases and exact-symbol entry retained when live lookup is unavailable. The
Stock Analysis input can append market suffixes from a selector and reports the
inferred native quote currency and a market-appropriate benchmark. Newly listed,
suspended, delisted, or thinly covered securities may have insufficient price or
fundamental observations.

## Tests

The scaffold check requires only Python:

```bash
python scripts/check_structure.py
```

The data-loader unit tests use an injected provider and therefore do not require
network access:

```bash
python -m unittest discover -s backend/tests/unit -p "test_*.py" -v
```

Run the live data-quality validation for the six-stock sample universe with:

```bash
python scripts/validate_market_data.py
```

This checks schema consistency, date coverage, ordering, duplicates, missing
values, numeric types, OHLC relationships, volume, and latest-observation age.
It writes a detailed local JSON report to
`artifacts/validation/market_data_validation.json`; generated reports remain
untracked by Git.

The validation run on 2026-09-29 passed for AAPL, MSFT, NVDA, TSLA, AMZN, and
GOOGL. Each series contained 2,951 daily observations from 2015-01-02 through
2026-09-28. See [docs/data_validation.md](docs/data_validation.md) for the
reproducible validation record and its limitations.

## Return and risk analysis

Run the standard financial analysis for one ticker with:

```bash
python scripts/analyze_stock.py NVDA
```

To use a 4% annual effective risk-free rate and save a local JSON artifact:

```bash
python scripts/analyze_stock.py NVDA \
  --risk-free-rate 0.04 \
  --output artifacts/analysis/nvda_metrics.json
```

The standard summary includes geometric annualized return, annualized sample
volatility, annualized Sharpe ratio, maximum drawdown, and one-day historical
VaR. Daily, monthly, and annual return-series functions are also exposed from
`app.quant.metrics`. See [docs/financial_metrics.md](docs/financial_metrics.md)
for definitions, sign conventions, and limitations.

On 2026-09-29, the end-to-end NVDA run over 2015-01-02 through 2026-09-28
produced a 69.30% annualized return, 48.11% annualized volatility, 1.3338 Sharpe
ratio, -66.34% maximum drawdown, and 4.42% one-day 95% historical VaR. This
descriptive historical result uses a 0% risk-free rate and is not a forecast.

## Factor ranking

Build the Value, Momentum, and Quality ranking for the default sample universe:

```bash
python scripts/rank_stocks.py
```

Or supply a custom cross-section:

```bash
python scripts/rank_stocks.py AAPL MSFT NVDA TSLA AMZN GOOGL
```

The script uses current fundamental snapshots and trailing adjusted-price
momentum. It writes its detailed, time-sensitive JSON result to
`artifacts/analysis/factor_ranking.json`, which is excluded from Git.

The retrieval on 2026-09-29 produced the following universe-relative ranking:

| Rank | Ticker | Value | Momentum | Quality | Quant Score |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | GOOGL | 80.00 | 53.33 | 66.67 | 66.67 |
| 2 | NVDA | 33.33 | 66.67 | 93.33 | 64.44 |
| 3 | MSFT | 66.67 | 73.33 | 46.67 | 62.22 |
| 4 | AMZN | 93.33 | 33.33 | 20.00 | 48.89 |
| 5 | AAPL | 13.33 | 73.33 | 46.67 | 44.44 |
| 6 | TSLA | 13.33 | 0.00 | 26.67 | 13.33 |

All six records had 100% component coverage. Scores are relative to this small
universe and retrieval time; they are not expected returns or recommendations.
The dashboard constructs a six-name research cross-section for US, China
A-share, and Hong Kong symbols. It uses the target company's current Yahoo
sector and market capitalization, prioritizes same-sector candidates, and then
ranks candidates by broad native-currency capitalization proximity. The target
and five peers come from a documented, deterministic market catalog so the
selection is reproducible and does not add dozens of provider calls. The API and
bilingual UI disclose the selection method, normalized sector, capitalization
band, realized universe, and data coverage. Other international suffixes remain
supported for price and risk analysis but use an explicitly labeled global
fallback until dedicated local catalogs are configured.

The Stock Analysis page can also replace automatic selection with 2-9 custom
Yahoo Finance peer symbols. The target is added automatically, duplicate symbols
are rejected, and cross-market custom samples are explicitly marked as not
market-matched. Every response includes the realized peer ranking, nine raw
factor inputs, factor-level scores and coverage. The same table can be inspected
in the dashboard or exported to CSV for an auditable research appendix.
Two diagnostic views make the cross-section easier to audit: an equal-weight
waterfall decomposes the composite score into Value, Momentum, and Quality
contributions, while small-multiple distributions place the target's PE, PB,
and EV/EBITDA beside available peers. Missing and nonpositive valuation
multiples are excluded and shown as unavailable rather than converted to zero.
See [docs/factor_model.md](docs/factor_model.md) for the complete methodology.

## Portfolio optimization, Monte Carlo simulation, and backtesting

Run the default AAPL/MSFT/NVDA/TSLA analysis with a fixed 15% cash reserve:

```bash
python scripts/optimize_portfolio.py
```

Key options include `--risk-free-rate`, `--cash-weight`, `--min-weight`,
`--max-weight`, `--frontier-points`, `--initial-value`, `--simulation-paths`,
and `--seed`. For example:

```bash
python scripts/optimize_portfolio.py AAPL MSFT NVDA TSLA \
  --cash-weight 0.15 \
  --max-weight 0.60 \
  --simulation-paths 10000 \
  --seed 42
```

The command writes a detailed JSON artifact to
`artifacts/analysis/portfolio_optimization.json` and a self-contained interactive
Plotly report to `outputs/portfolio_analysis.html`.

The recorded run on 2026-09-29 produced this maximum-Sharpe allocation:

| Asset | Weight |
| --- | ---: |
| AAPL | 20.33% |
| MSFT | 6.48% |
| NVDA | 51.17% |
| TSLA | 7.01% |
| Cash | 15.00% |

Its historical-estimate summary was 42.97% expected annual return, 31.22%
annualized volatility, and a 1.3766 Sharpe ratio using a 0% risk-free rate. A
$100,000 one-year, 10,000-path GBM simulation produced P5/mean/P95 terminal
values of $81,185 / $143,404 / $228,447 and a 16.02% simulated probability of
loss. These conditional model results are not forecasts.

The dashboard also performs a trailing-window walk-forward study. At every
rebalance date it re-estimates the maximum-Sharpe weights from data that were
available at that date, lets weights drift between rebalances, deducts a
configurable proportional trading cost from half-turnover, and compares the
result with a buy-and-hold benchmark. The automatic benchmark is SPY for US
universes, SSE Composite (`000001.SS`) for China A-share universes, Hang Seng (`^HSI`)
for Hong Kong universes, and ACWI for mixed-market universes; the user can
override it. The response includes wealth and
drawdown paths plus an auditable rebalance log; it does not reuse the
full-sample allocation as a historical strategy.

Portfolio returns currently use each asset's native quote-currency series.
Monetary outputs can be labeled USD, CNY, or HKD, but the model does not perform
foreign-exchange conversion. Cross-currency portfolios therefore require extra
caution and should not be interpreted as FX-adjusted performance.

The live validation on 30 September 2026 used a 756-trading-day lookback, a
63-trading-day rebalance interval, 10 bps transaction costs, a 15% cash reserve,
and the AAPL/MSFT/NVDA/TSLA universe. From 3 January 2018 through 29 September
2026, the hypothetical strategy recorded a 32.10% CAGR, 1.026 Sharpe ratio,
-55.67% maximum drawdown, and $2,190 cumulative modeled trading cost across 35
rebalances. SPY recorded a 14.39% CAGR over the same displayed period. These
time-sensitive results are subject to universe selection, survivorship bias,
unstable estimates, and simplified execution assumptions.

The same run reported a 1.499 Sortino ratio, 22.04% annualized downside
deviation, 1.267 beta and 0.748 return correlation versus SPY, 21.98% tracking
error, and a 421-trading-day longest underwater period. A configurable rolling
risk window plots the strategy and benchmark volatility together with rolling
beta, making changing risk exposure visible rather than reducing the study to
one terminal performance number.

An optional parameter-robustness endpoint evaluates a 3-by-3 grid of 252/504/756
day estimation windows and 21/63/126 day rebalance schedules. Every cell is
aligned to the longest lookback's out-of-sample start, so results share identical
evaluation dates. In the recorded run, scenario CAGR ranged from 32.10% to
40.43%, with a 35.40% median, 1.078 median Sharpe ratio, and -56.60% worst grid
drawdown. All nine scenarios exceeded SPY CAGR in this selected surviving-stock
universe; this is robustness evidence within the grid, not independent proof of
future excess returns.

See [docs/portfolio_optimization.md](docs/portfolio_optimization.md) for the
estimator, constraint, simulation, backtest, and limitation details.

## Machine-learning experiment

Run the leakage-aware NVDA five-day return experiment with:

```bash
python scripts/run_ml_experiment.py NVDA --lstm-epochs 25 --seed 42
```

The experiment constructs 15 trailing price, volume, and technical features,
uses chronological train/validation/test partitions with a five-day purge gap,
and compares Linear Regression, XGBoost, and a PyTorch LSTM against a
zero-return baseline. All four models are evaluated on the same test dates.
Training-only scaling and validation early stopping are used where applicable.

Current fundamental snapshots are intentionally excluded because applying
today's ratios to historical dates would create look-ahead bias. The feature
pipeline accepts fundamentals only as dated point-in-time history and never
backfills them before their availability dates.

The recorded 29 September 2026 NVDA run used 551 common test observations from
11 July 2024 through 21 September 2026:

| Model | RMSE | MAE | Direction Accuracy |
| --- | ---: | ---: | ---: |
| LSTM | 0.06148 | 0.04779 | 56.08% |
| Linear Regression | 0.06163 | **0.04778** | 55.54% |
| XGBoost | 0.06197 | 0.04797 | 56.08% |
| Zero-Return Baseline | 0.06203 | 0.04807 | 0.00% |

The improvements over the naive error baseline were small and do not establish
market predictability. The command writes a detailed JSON artifact to
`artifacts/analysis/ml_nvda_report.json` and a self-contained Plotly report to
`outputs/ml_model_comparison.html`. See
[docs/machine_learning.md](docs/machine_learning.md) for the feature definitions,
experimental protocol, interpretation, and limitations.

## Research dashboard

Start the FastAPI backend from the repository root:

```bash
python -m uvicorn app.main:app --app-dir backend --reload
```

In another terminal, start the Next.js frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:3000`. The dashboard contains:

- **Market Overview** for the S&P 500, NASDAQ Composite, VIX, and Bitcoin;
- **Stock Analysis** with TradingView OHLCV visualization, financial and risk
  metrics, current factor scores, saved ML experiment evidence, a browser-local
  research watchlist, global company-name and ticker search,
  Shanghai/Shenzhen/Hong Kong symbol helpers,
  market-matched factor references, shareable ticker URLs, and JSON/CSV exports;
- **Portfolio Optimizer** with constrained allocations, Plotly efficient
  frontier, Monte Carlo percentile bands, trailing-only walk-forward validation,
  selectable market-aware benchmarks and drawdown comparisons, native-currency
  disclosure, downside and benchmark-relative risk diagnostics,
  rolling volatility and beta, an on-demand common-period parameter sensitivity
  grid, an auditable rebalance log, constraint feasibility checks, shareable input
  URLs, and allocation/backtest/grid/full-result exports.

The interface supports English and Simplified Chinese across navigation,
forms, metric labels, chart legends, model assumptions, disclaimers, and AI
research explanations. The language preference is stored in the browser. The
visual system uses an admissions-oriented academic-finance style: a light
report surface, navy research navigation, restrained teal accents, and
high-contrast data cards.

The practical research utilities are deliberately local-first. Watchlist symbols
remain in browser storage, CSV and JSON files are generated in the browser, and
shared portfolio URLs contain model inputs rather than frozen or advisory results.
If a stock, portfolio asset, or benchmark cannot be loaded, the API returns a
structured list of every unavailable symbol and the bilingual interface presents
an actionable retry-or-remove message rather than a generic provider exception.

The API exposes typed response contracts and interactive OpenAPI documentation
at `http://localhost:8000/docs`. See [docs/dashboard.md](docs/dashboard.md) for
routes, architecture, configuration, and limitations.

### Public deployment

The repository includes a Render Blueprint for the FastAPI service, a lightweight
Web dependency set, environment-configurable CORS, and Vercel configuration for
the Next.js frontend. See [docs/deployment.md](docs/deployment.md) for the complete
GitHub → Render → Vercel procedure, production environment variables, smoke tests,
and hosting limitations.

## Explainable-AI summaries

The Stock Analysis page includes a constrained narrative layer that explains
only the metrics already computed by QuantAI. Configure the server-side OpenAI
credentials before starting FastAPI:

```bash
export OPENAI_API_KEY="your_key_here"
export OPENAI_MODEL="gpt-6-luna"
```

On PowerShell use `$env:OPENAI_API_KEY="your_key_here"` and
`$env:OPENAI_MODEL="gpt-6-luna"` in the terminal that starts FastAPI. The root
`.env.example` is a deployment template; QuantAI does not automatically load a
local `.env` file.

The backend uses the OpenAI Responses API with a Pydantic Structured Outputs
schema and disables response storage for this request. The browser never sees
the API key and cannot send a free-form prompt. If the key is absent or the
provider is unavailable, the endpoint returns a labeled deterministic summary
from the same evidence bundle instead of failing the research page.

The API route is `GET /api/v1/stocks/{ticker}/explanation`, with `locale=en`
or `locale=zh-CN`. Every response
includes metric evidence, interpretation limits, its generation source, and an
explicit no-investment-advice disclaimer. See
[docs/explainability.md](docs/explainability.md) for the boundary and test
design.

## Data and reproducibility policy

- Raw market data, local databases, generated models, and secrets are excluded from Git.
- Configuration templates and deterministic tests remain version controlled.
- Financial results will include dates, assumptions, units, and methodology where applicable.
- Machine-learning results will use time-aware validation to reduce look-ahead bias.

## Disclaimer

This repository is for education and research only. Outputs are not investment recommendations, and historical or simulated performance does not guarantee future results.
