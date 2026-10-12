# Financial Metric Methodology

## Price convention

Return and drawdown calculations use `adjusted_close` by default so historical
corporate actions are reflected in the return series. Raw OHLC prices remain
available for price-chart and trading-range analysis.

## Return series

Daily simple return:

```text
r_t = P_t / P_(t-1) - 1
```

Monthly and annual returns use the last available adjusted close in each
calendar month or year. The first sampled period is omitted because the input
window has no preceding period-end price.

Geometric annualized return from daily returns:

```text
annualized_return = product(1 + r_t)^(252 / N) - 1
```

## Risk metrics

- **Annualized volatility:** sample standard deviation of daily returns times
  the square root of 252.
- **Sharpe ratio:** mean daily excess return divided by its sample standard
  deviation, multiplied by the square root of 252. The configured annual
  effective risk-free rate is converted to a daily effective rate first.
- **Maximum drawdown:** the most negative value of `P_t / running_peak_t - 1`.
  It is reported as a negative percentage.
- **Historical VaR:** the empirical lower-tail daily return quantile, reported as
  a nonnegative loss magnitude. A 95% VaR of 2.5% means the observed one-day
  loss threshold at that confidence level is 2.5%; it is not a maximum loss.

## Assumptions and limitations

- The default annualization factor is 252 trading days.
- Returns exclude transaction costs, taxes, slippage, and portfolio cash flows.
- The default risk-free rate is 0% unless explicitly supplied.
- Square-root-of-time annualization does not model volatility clustering.
- Historical VaR depends on the selected sample, treats observations as an
  empirical distribution, and does not describe losses beyond the threshold.

## Recorded end-to-end validation

On 29 September 2026, `scripts/analyze_stock.py NVDA` was run against live data
using the default start date and a 0% annual effective risk-free rate.

| Measure | Result |
| --- | ---: |
| Observation window | 2015-01-02 to 2026-09-28 |
| Price observations | 2,951 |
| Annualized return | 69.30% |
| Annualized volatility | 48.11% |
| Sharpe ratio | 1.3338 |
| Maximum drawdown | -66.34% |
| Historical VaR, 95% daily | 4.42% loss |

These values are a reproducibility snapshot of one historical sample. They may
change when the vendor revises data or the observation window advances, and
they are neither a forecast nor an investment recommendation.
