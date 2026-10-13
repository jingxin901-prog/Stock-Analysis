# QuantAI: An Explainable AI-Powered Portfolio Optimization and Risk Analysis Platform

## Abstract

QuantAI is an end-to-end quantitative research platform combining standardized
market data, return and risk measurement, cross-sectional factors, constrained
portfolio optimization, Monte Carlo simulation, leakage-aware machine learning,
walk-forward historical validation, and evidence-grounded language-model
explanations. The implementation emphasizes typed interfaces, reproducibility,
explicit assumptions, and separation between research evidence and investment
advice. Empirical examples demonstrate the workflow while also showing that
historical fit, simulated distributions, and small holdout improvements do not
establish future predictability.

## 1. Introduction

Quantitative investment research is valuable not because a single model can
remove market uncertainty, but because a disciplined pipeline makes data,
assumptions, validation, and limitations inspectable. QuantAI was developed as a
portfolio-scale research system rather than a stock-direction prediction demo.
It connects data ingestion to descriptive statistics, factor ranking,
optimization, simulation, time-aware model evaluation, and a bilingual web
interface. The central design objective is to make each numerical result
reproducible and each narrative claim traceable to computed evidence.

## 2. Data

Historical daily market data are retrieved from Yahoo Finance through the
`yfinance` Python package. The initial research window begins on 1 January 2015
and ends at the latest observation available at retrieval time unless an
exclusive end date is supplied.

The implementation accepts Yahoo Finance symbols across markets, including
Shanghai (`.SS`), Shenzhen (`.SZ`), and Hong Kong (`.HK`). A deterministic
symbol-context layer discloses the inferred quote currency and selects a default
market benchmark without an additional provider request. The presentation layer
also exposes cached ticker and company-name discovery. It combines live Yahoo
Finance search results with a small bilingual alias catalog and preserves direct
exact-symbol entry when discovery is unavailable.

The ingestion layer preserves raw open, high, low, and close prices and stores
adjusted close separately. This distinction allows later return calculations to
account for corporate actions without obscuring the observed historical trading
range. Provider responses are normalized to an ascending, duplicate-free daily
index. Rows missing any required OHLCV field are excluded and the number of
received and retained observations is recorded as DataFrame metadata.

After successful standardization, an exact-request CSV snapshot is written to a
local cache. This cache is consulted only when a later live provider request
fails. Cached responses carry their persistence timestamp and last observation
date through the typed API and dashboard, so resilience does not blur the
distinction between stale and live market data.

Normalized fundamental snapshots use a separate atomic JSON cache. A provider
failure may recover the last useful company, sector, capitalization, and ratio
snapshot, while the API marks its source and the factor result as non-current.
This improves exploratory continuity without representing cached fundamentals
as point-in-time or live observations.

Yahoo Finance is a convenient research source rather than an institutional
point-in-time database. Later empirical sections must therefore discuss vendor
revisions, delisted-security coverage, survivorship bias, and the absence of a
formal data-service guarantee.

### 2.1 Initial ingestion validation

On 29 September 2026, the ingestion pipeline was tested against AAPL, MSFT,
NVDA, TSLA, AMZN, and GOOGL. All six downloads contained 2,951 standardized
daily observations from 2 January 2015 through 28 September 2026. Every series
passed the schema, ordering, uniqueness, missing-value, numeric-type, OHLC,
volume, start-coverage, and recency checks. This establishes pipeline integrity
for the initial sample but is not an independent verification of vendor prices.

## 3. Methodology

### 3.1 Return and risk measurement

Simple daily returns are calculated from adjusted closing prices. Monthly and
annual return series use the last available adjusted close in each calendar
period. The summary annualized return is the geometric compounded daily return
scaled to 252 trading days. Volatility is the daily sample standard deviation
scaled by the square root of 252.

The Sharpe ratio uses arithmetic mean daily excess return and sample standard
deviation, annualized by the square root of 252. An annual effective risk-free
rate is converted to a daily effective rate before subtraction. Maximum
drawdown is the minimum percentage decline from a running adjusted-price peak.
Historical Value at Risk is the empirical lower-tail daily-return quantile and
is reported as a positive loss magnitude.

### 3.2 Factor construction

The current cross-sectional model combines Value, Momentum, and Quality. Value
uses positive trailing PE, price-to-book, and enterprise-value-to-EBITDA, with
lower values preferred. Momentum uses 3-, 6-, and 12-calendar-month adjusted
price returns, with higher returns preferred. Quality uses return on equity,
profit margin, and debt-to-equity leverage, preferring higher profitability and
lower nonnegative leverage.

The interactive analysis constructs a compact comparison set using a
version-controlled candidate catalog. For US, China A-share, and Hong Kong
targets, it first restricts candidates to the same market, prioritizes the
target's normalized current sector, and then orders candidates by proximity to
a broad native-currency market-capitalization band. The API records this
selection method, sector, size band, realized peer universe, and component data
coverage. Missing metadata triggers a disclosed same-market fallback; markets
without a dedicated catalog use a disclosed global fallback. This approach is
reproducible and latency-bounded, but the catalog remains researcher selected.

The interface additionally supports researcher-defined comparison sets of two
to nine peers. Custom samples preserve the target as the focal observation and
are explicitly flagged when they cross markets. The typed response retains the
nine raw inputs, factor and composite scores, ranks, and coverage for every
realized peer, enabling CSV export and replication of the displayed
cross-section.

Each component is winsorized at the cross-sectional 5th and 95th percentiles and
converted to a direction-aware percentile score from 0 to 100. Missing or
economically invalid components receive a neutral score of 50 while reducing
the disclosed coverage ratio. Component scores are equally weighted within
each factor, and the three factors are equally weighted in the composite Quant
Score. This is a current-snapshot comparison, not a point-in-time backtest.
The dashboard uses compact market-matched reference universes for US, China
A-share, and Hong Kong listings. Other international listings receive a clearly
labeled fallback comparison rather than an implied same-market ranking.

For interpretation, the dashboard decomposes the composite through an
equal-weight factor-contribution waterfall and displays PE, PB, and EV/EBITDA
small multiples for the realized peers, with the target highlighted. These are
descriptive cross-sectional diagnostics. Nonfinite, missing, and nonpositive
valuation multiples are excluded and surfaced as unavailable rather than
imputed to zero.

### 3.3 Portfolio optimization

Adjusted-price series are inner-aligned before daily simple returns are
calculated. Expected annual returns are estimated as arithmetic mean daily
return multiplied by 252. Covariance is estimated either as daily sample
covariance or with Oracle Approximating Shrinkage (OAS), then annualized by 252.
OAS estimates a window-specific shrinkage intensity and pulls the empirical
matrix toward a scaled identity target to reduce sampling noise and poor
conditioning. Sequential Least Squares Programming solves the
long-only maximum-Sharpe and global minimum-volatility problems under explicit
cash, minimum-weight, and maximum-weight constraints. Repeated
minimum-volatility solutions at increasing target returns trace the upper
efficient frontier.

The dashboard treats sample covariance as a classical baseline and OAS as the
default robust estimator. Both are evaluated with identical constraints,
trailing windows, rebalance dates, benchmark, and transaction costs. The
comparison reports matrix condition numbers, in-sample portfolio statistics,
and cost-inclusive walk-forward CAGR, volatility, Sharpe ratio, maximum
drawdown, and turnover. This design isolates the covariance choice but does not
resolve expected-return uncertainty or turn historical selection into a
forecast.

### 3.4 Monte Carlo simulation

The optimized maximum-Sharpe portfolio is simulated under geometric Brownian
motion with constant drift and volatility. The default experiment contains
10,000 paths over 252 trading days and uses a stored random seed. Log drift is
calibrated so expected one-year terminal value is consistent with the supplied
simple annual return. Scenario summaries use the 5th percentile, mean, and 95th
percentile terminal values rather than unstable sample extrema.

### 3.5 Walk-forward portfolio validation

At each scheduled rebalance date, the backtest uses only the preceding trailing
window to estimate expected returns and covariance and solve the constrained
maximum-Sharpe allocation. The resulting positions drift with realized returns
until the next rebalance. Turnover is one-half of the absolute change across
risky and cash weights, and a configurable proportional cost is deducted at the
start of each holding segment. The first deployment from cash also incurs cost.
The strategy is compared with an equal-starting-value buy-and-hold benchmark.
Defaults are SPY for US universes, SSE Composite for China A-shares, Hang Seng for Hong
Kong listings, and ACWI for mixed-market universes; the request may override the
benchmark explicitly.

This design avoids the direct look-ahead error of applying a full-sample optimum
to earlier dates. The response retains every dated target weight, turnover, and
cost so decisions can be audited. It does not eliminate universe selection,
survivorship bias, parameter selection, vendor revision, or simplified execution
assumptions.

The realized cost-inclusive strategy return path is also evaluated through
downside deviation and the Sortino ratio, together with beta, correlation,
tracking error, and information ratio relative to SPY. Consecutive observations
below the running wealth peak measure drawdown duration. Rolling annualized
volatility and beta use a separately disclosed trailing window and remain
missing until a complete window exists.

Parameter robustness is evaluated over a grid of estimation lookbacks and
rebalance intervals. Every scenario is truncated so its first investable date
matches the date implied by the largest lookback. This common-period design
prevents a shorter lookback from receiving credit for an earlier or easier
market regime. Each grid cell reruns optimization, weight drift, turnover, and
transaction costs; summary statistics describe dispersion rather than selecting
only the best-performing cell.

### 3.6 Machine-learning experiments

The supervised-learning experiment predicts the next five-trading-day simple
adjusted-price return. Fifteen trailing features describe returns, volume,
moving-average gaps, RSI, MACD, realized volatility, and intraday price range.
All features are measurable by the prediction date. The current fundamental
snapshot is excluded because it is not point-in-time history; optional
fundamental inputs must instead carry real availability dates and are only
forward-filled after release.

Data are divided chronologically into 60% training, 20% validation, and 20%
testing partitions. Five observations are purged before both validation and
test boundaries to prevent a five-day label from crossing into the next
partition. Linear Regression, XGBoost, and a 30-day PyTorch LSTM are compared
with a zero-return baseline. Scaling parameters are fitted only on training
data, XGBoost and LSTM use the validation partition for early stopping, and all
models are evaluated on the identical post-lookback test dates. RMSE, MAE, and
exact-sign direction accuracy are reported.

### 3.7 Evidence-grounded language-model explanation

The explanation layer operates after the quantitative pipeline and cannot
alter calculations. It receives a compact typed record containing factor
scores, annualized return and volatility, maximum drawdown, historical VaR,
the displayed experiment status, and prewritten methodological limitations.
The backend assigns a transparent descriptive risk label using annualized
volatility thresholds below 25%, from 25% to below 45%, and 45% or above.

When configured, an OpenAI model produces only a concise summary and two to
four observations under a Pydantic Structured Outputs schema. The model is
instructed not to introduce news, causes, forecasts, price targets, or trading
recommendations. Evidence cards, risk classification, limitations, source
label, and disclaimer are controlled by application code. A deterministic
template processes the identical evidence when no API key is available or a
provider request fails.

## 4. Experiments

The initial machine-learning experiment uses NVDA observations beginning in
2015. After feature warm-up and target alignment, the training partition
contains 1,733 observations from 16 March 2015 through 28 January 2022; the
validation partition contains 574 observations from 7 February 2022 through 20
May 2024; and the test partition contains 580 observations from 29 May 2024
through 21 September 2026. A 30-day within-partition LSTM lookback leaves 551
common evaluation dates beginning 11 July 2024. The experiment fixes its random
seed at 42 and records model settings and daily predictions in a JSON artifact.

The portfolio validation experiment uses AAPL, MSFT, NVDA, and TSLA, a fixed
15% cash reserve, a 60% asset cap, a 756-trading-day lookback, rebalancing every
63 trading days, 10 bps proportional trading cost, and SPY as benchmark. The
initial value is $100,000 and the historical path begins only after the first
complete estimation window.

The robustness experiment crosses 252-, 504-, and 756-day estimation windows
with 21-, 63-, and 126-day rebalance intervals. All nine scenarios use the same
3 January 2018 through 29 September 2026 evaluation period.

## 5. Results

The initial live-data validation passed for all six sample securities. Financial
metric formulas were then tested against deterministic examples before an
end-to-end NVDA calculation was performed. Over 2 January 2015 through 28
September 2026, and using a 0% annual effective risk-free rate, the NVDA sample
produced a 69.30% geometric annualized return, 48.11% annualized volatility,
1.3338 Sharpe ratio, -66.34% maximum drawdown, and 4.42% one-day 95% historical
VaR. These are historical descriptive statistics rather than predictive results.

The current factor model was then evaluated on the six-stock sample universe.
GOOGL ranked first with a Quant Score of 66.67, followed by NVDA at 64.44 and
MSFT at 62.22. AMZN, AAPL, and TSLA scored 48.89, 44.44, and 13.33 respectively.
All securities had complete coverage of the nine requested components. These
scores are universe-relative snapshots and do not constitute expected-return
estimates.

The portfolio experiment used AAPL, MSFT, NVDA, and TSLA with a fixed 15% cash
reserve and 60% per-asset cap. The maximum-Sharpe risky allocation was 20.33%
AAPL, 6.48% MSFT, 51.17% NVDA, and 7.01% TSLA. Historical sample estimates gave
a 42.97% expected annual return, 31.22% annualized volatility, and 1.3766 Sharpe
ratio. For a $100,000 initial value, the 10,000-path one-year simulation yielded
P5, mean, and P95 terminal values of approximately $81,185, $143,404, and
$228,447. The simulated loss probability was 16.02%. These results are
conditional on unstable historical mean and covariance estimates and a
lognormal constant-parameter simulation model.

The trailing-window validation retrieved through 29 September 2026 produced 35
rebalance decisions from 3 January 2018. The hypothetical strategy recorded a
32.10% CAGR, 1.026 Sharpe ratio, -55.67% maximum drawdown, and $2,190 cumulative
modeled trading cost. The displayed SPY benchmark recorded a 14.39% CAGR over
the same period. The strategy's higher return came with a severe drawdown and
cannot be interpreted as expected outperformance: the universe consists of
surviving large-cap winners selected with hindsight, and model parameters were
not chosen through an independent preregistered protocol.

The same path had a 1.499 Sortino ratio and 22.04% annualized downside
deviation. Its beta and return correlation relative to SPY were 1.267 and 0.748,
respectively; tracking error was 21.98% and the information ratio was 0.809. The
strategy remained below a previous peak for as many as 421 consecutive trading
observations, compared with 488 for SPY. These diagnostics show that the higher
retrospective return did not imply low risk or rapid recovery.

Across the nine common-period parameter scenarios, CAGR ranged from 32.10% to
40.43% and had a 35.40% median. Median Sharpe ratio was 1.078, and the worst
maximum drawdown was -56.60%. Every tested scenario exceeded the 14.39% SPY CAGR.
This consistency reduces concern that the displayed result depends entirely on
one lookback or rebalance choice, but it does not address hindsight in the
selected stock universe, tested grid, or benchmark.

On the 551-date NVDA machine-learning holdout, the LSTM obtained an RMSE of
0.06148, MAE of 0.04779, and 56.08% direction accuracy. Linear Regression
obtained 0.06163 RMSE, 0.04778 MAE, and 55.54% direction accuracy. XGBoost
obtained 0.06197 RMSE, 0.04797 MAE, and 56.08% direction accuracy. The
zero-return baseline had 0.06203 RMSE and 0.04807 MAE. Error improvements were
therefore small: the result demonstrates a disciplined experimental pipeline,
not reliable market prediction or economic profitability.

The explanation experiment was verified in deterministic mode and with an
injected structured-output provider boundary. Tests confirmed that missing
credentials and provider failures return a labeled evidence-based fallback,
while a successful provider result preserves the server-computed risk label,
evidence, limitations, and no-advice disclaimer.

## 6. Limitations

Yahoo Finance is not an institutional point-in-time data source, and the small
current universe is exposed to survivorship and selection bias. Historical
mean returns and covariance are unstable, while the Monte Carlo model assumes
constant parameters and lognormal paths. Factor scores are cross-sectional
snapshots rather than backtested portfolios.

International price series remain denominated in their native quote currencies.
The portfolio model labels the monetary display unit but does not translate
returns through historical foreign-exchange rates. Cross-currency covariance,
wealth paths, and benchmark-relative statistics are therefore not FX-adjusted.

The machine-learning result covers one security and one terminal holdout
period. Its five-day targets overlap, adjacent errors are therefore dependent,
and no multiple-testing or statistical-significance adjustment is reported.
Hyperparameters are illustrative. The portfolio backtest incorporates a simple
proportional transaction-cost input, but none of the current experiments models
bid-ask spread variation, market impact, latency, taxes, borrow availability, or
a tradable execution protocol.

The completed presentation layer uses typed FastAPI endpoints and a Next.js
dashboard to expose the research results. This separation keeps analytical
formulas independent of HTTP and visualization concerns. The interface was
validated against live provider responses for the market overview, NVDA stock
analysis, and the four-asset portfolio experiment. It remains a local research
prototype without authentication, distributed caching, rate limiting, or
institutional data-service guarantees.

The presentation layer supports English and Simplified Chinese through a typed
message catalog and a locale-aware explanation endpoint. Language changes do not
alter numerical calculations. Both desktop and narrow mobile layouts were
visually checked in the admissions-oriented academic-finance design.

To support repeatable practical use, the stock workflow includes a browser-local
watchlist, bilingual company-name and ticker search, ticker-addressable URLs, and
structured price and research exports.
The portfolio workflow adds input presets, client-side feasibility screening,
shareable configuration URLs, selectable covariance estimators, a matched
sample-versus-OAS stability table, and allocation/full-result exports. These tools
improve reproducibility while keeping historical model output separate from
investment advice.

Language-model prose can still be incomplete or misleading even when its input
and schema are constrained. QuantAI therefore presents the underlying values
next to the narrative, labels whether OpenAI or the deterministic path produced
the text, and treats the prose as a presentation aid rather than a new model
result.

## 7. Conclusion

QuantAI demonstrates a complete and testable quantitative research workflow
without presenting historical output as investment advice. Its most important
result is methodological: the same platform exposes data quality, estimator
choices, portfolio constraints, hypothetical execution costs, time-aware model
evaluation, and interpretation limits. The walk-forward module strengthens the
portfolio experiment by replacing in-sample historical storytelling with a
sequence of trailing-only decisions, while the recorded drawdown illustrates
why even strong retrospective growth demands careful risk interpretation.

## 8. Future Work

Planned extensions include user-configurable robustness grids, historical FX
conversion, additional local peer catalogs beyond the currently supported US,
China A-share, and Hong Kong markets, cross-asset and delisted-security
universes, nested validation of
parameter choices, non-overlapping-target robustness checks, uncertainty
estimates, timestamped fundamental histories, PostgreSQL persistence,
production deployment controls, prompt-regression evals, and monitored
explanation quality.
