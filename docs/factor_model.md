# Factor Model Methodology

## Scope

QuantAI currently produces a retrieval-time cross-sectional ranking. It does not
yet construct a historically point-in-time factor backtest. Current fundamental
snapshots must therefore not be joined to past prices and presented as if those
fundamentals had been known historically.

## Raw components

### Value

- Trailing price-to-earnings ratio (`trailingPE`)
- Price-to-book ratio (`priceToBook`)
- Enterprise-value-to-EBITDA (`enterpriseToEbitda`)

Lower positive multiples score better. Nonpositive multiples are treated as
economically non-comparable rather than as unusually cheap.

### Momentum

- Trailing 3-calendar-month adjusted-price return
- Trailing 6-calendar-month adjusted-price return
- Trailing 12-calendar-month adjusted-price return

For each horizon, the baseline is the last available trading observation on or
before the calendar lookback date. Higher returns score better.

### Quality

- Return on equity (`returnOnEquity`)
- Profit margin (`profitMargins`)
- Leverage proxy (`debtToEquity / 100`)

Higher ROE and profit margin score better. Lower nonnegative leverage scores
better. The leverage component is named `debt_ratio` in the normalized factor
contract, but it is specifically debt-to-equity and not debt divided by assets.

## Comparable peer construction

For US, China A-share, and Hong Kong targets, the dashboard selects a compact
six-name cross-section: the requested stock plus five candidates from the same
market. The target's current Yahoo Finance sector and market capitalization are
used to prioritize the same normalized sector and then the nearest broad
capitalization band. Native-currency thresholds are disclosed in code and avoid
false precision across USD, CNY, and HKD. If current metadata are unavailable,
known catalog metadata or a deterministic same-market fallback is used. Other
international markets use an explicitly labeled global fallback.

The candidate catalog is intentionally curated and version-controlled. This
makes a displayed ranking reproducible and keeps request latency bounded, but it
also introduces researcher selection and survivorship bias. The returned API
contract therefore records the selection method, peer sector, capitalization
band, realized universe, and data coverage.

Researchers may instead provide 2-9 custom peer symbols. QuantAI adds the target
security, removes it from the peer input if repeated, rejects duplicate or
malformed symbols, and discloses whether all requested securities share the
target market. The returned ranking contains all nine raw components, the three
factor scores, composite score, ranks, and factor-level coverage. Peers whose
price histories cannot be loaded are omitted from the realized cross-section,
so the requested and realized sample sizes may differ.

## Visual diagnostics

The dashboard renders the composite as an equal-weight waterfall, where each
factor contributes one third of its 0-100 score. This is a score decomposition,
not a return-attribution analysis. It also plots PE, PB, and EV/EBITDA across
the realized peer set and highlights the target security. Only finite positive
multiples are comparable; missing and nonpositive values remain visibly
unavailable and are never represented as zero.

## Scoring

1. Convert inputs to finite numeric values.
2. Treat nonpositive valuation multiples and negative leverage as missing.
3. Winsorize each component at the cross-sectional 5th and 95th percentiles.
4. Convert each component to a 0-100 percentile score in the economically
   appropriate direction.
5. Assign missing components a neutral score of 50 and disclose factor-level
   and total data coverage.
6. Average three component scores within each factor.
7. Equally weight Value, Momentum, and Quality to obtain `quant_score`.
8. Rank descending by score, then coverage, then ticker for deterministic ties.

Scores are universe-relative. A score of 80 means a stock compares favorably
within the supplied cross-section; it is not an 80% probability of a positive
return and is not an investment recommendation.

## Recorded cross-sectional validation

On 29 September 2026, the model was run on AAPL, MSFT, NVDA, TSLA, AMZN, and
GOOGL. All nine factor components were present for every security.

| Rank | Ticker | Value | Momentum | Quality | Quant Score | Coverage |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | GOOGL | 80.00 | 53.33 | 66.67 | 66.67 | 100% |
| 2 | NVDA | 33.33 | 66.67 | 93.33 | 64.44 | 100% |
| 3 | MSFT | 66.67 | 73.33 | 46.67 | 62.22 | 100% |
| 4 | AMZN | 93.33 | 33.33 | 20.00 | 48.89 | 100% |
| 5 | AAPL | 13.33 | 73.33 | 46.67 | 44.44 | 100% |
| 6 | TSLA | 13.33 | 0.00 | 26.67 | 13.33 | 100% |

The result is intentionally reported as a validation snapshot. Rankings may
change when prices move, financial statements update, vendor fields are revised,
or the comparison universe changes.
