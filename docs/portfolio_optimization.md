# Portfolio Optimization and Simulation Methodology

## Historical estimates

Adjusted closing prices are inner-aligned across the selected universe. Daily
simple returns are used to estimate:

- annual expected return as arithmetic mean daily return times 252;
- annual covariance as daily sample covariance times 252.

These estimates are highly sensitive to the observation window and should not
be interpreted as stable forecasts.

## Markowitz optimization

QuantAI uses constrained Sequential Least Squares Programming (SLSQP) for:

1. the long-only maximum-Sharpe portfolio;
2. the long-only global minimum-volatility portfolio;
3. minimum-volatility portfolios across target expected returns to trace the
   upper efficient frontier.

Risky weights must sum to `1 - cash_weight` and each asset respects the supplied
minimum and maximum bounds. Cash is a fixed user-selected reserve earning the
configured annual risk-free rate. Fixing cash removes the otherwise non-unique
scale of a risk-free-plus-tangency allocation.

## Monte Carlo simulation

The maximum-Sharpe portfolio is simulated for 252 trading days with 10,000 paths
by default. The model uses geometric Brownian motion with constant annual drift
and volatility. Log drift is calibrated so expected one-year terminal value
matches the optimizer's expected simple annual return.

- Worst Case: 5th percentile terminal value
- Average Case: mean terminal value
- Best Case: 95th percentile terminal value

These labels are scenario summaries rather than literal minimum and maximum
outcomes. The random seed is stored for reproducibility.

## Walk-forward historical validation

The dashboard evaluates a sequence of genuinely historical decisions rather
than applying the final full-sample weights to the past. For each scheduled
rebalance date, QuantAI:

1. selects only the preceding `backtest_lookback_days` daily observations;
2. re-estimates annual arithmetic mean returns and annual covariance;
3. solves the same constrained long-only maximum-Sharpe problem;
4. deducts `transaction_cost_bps` from portfolio value using one-half of the
   absolute change in risky and cash weights as turnover; and
5. holds the resulting positions until the next `rebalance_days` interval,
   allowing asset weights to drift with realized returns.

The initial move from cash into the first target portfolio incurs trading cost.
Strategy and SPY paths begin at the same user-selected initial value. The API
returns total return, CAGR, annualized volatility, Sharpe ratio, maximum
drawdown, daily wealth and drawdown observations, total modeled cost, and the
complete dated rebalance log. Unit tests verify that changing observations
after a rebalance cannot change that rebalance's selected weights.

### Risk diagnostics

Risk diagnostics use the realized, cost-inclusive walk-forward return path.
Downside deviation is the annualized root mean square of returns below the
daily risk-free rate; the Sortino ratio divides annualized mean excess return by
that downside deviation. Full-period beta is strategy/benchmark covariance
divided by benchmark variance, while correlation is the Pearson return
correlation. Tracking error is the annualized sample standard deviation of
strategy-minus-benchmark daily returns, and the information ratio annualizes
their mean relative to that tracking error. The longest underwater period counts
consecutive trading observations below the previous wealth peak.

Rolling strategy volatility, benchmark volatility, and beta use the requested
`risk_window_days` observations. Early path points remain null until the first
complete window rather than being calculated from inconsistent sample lengths.

### Parameter robustness grid

The optional robustness study crosses two to five estimation lookbacks with two
to five rebalance intervals. To prevent incomparable performance windows, all
scenarios begin on the date made available by the largest lookback. A shorter
lookback receives a later input slice so it still has exactly its requested
training history before that common start date. Each cell reruns the complete
cost-inclusive walk-forward process.

The response reports each cell's CAGR, excess CAGR over SPY, Sharpe ratio,
maximum drawdown, average turnover, modeled cost, and rebalance count. Summary
statistics use the median scenario CAGR and Sharpe, worst drawdown, CAGR range,
and fraction of scenarios exceeding benchmark CAGR. The grid is intentionally
run on demand because it requires many more optimization solves than the primary
analysis.

## Limitations

- Sample means are noisy estimates of expected return.
- Sample covariance may change materially across market regimes.
- The single-period optimizer ignores taxes, liquidity, turnover penalties,
  and execution impact; the walk-forward layer models only a simple
  user-supplied proportional transaction cost.
- Long-only box constraints are modeling choices, not universal requirements.
- GBM assumes lognormal prices and constant parameters, understating jumps,
  volatility clustering, skewness, and extreme tails.
- Simulated outcomes are conditional model outputs, not forecasts or advice.
- The backtest uses a selected surviving stock universe and one benchmark, so
  it remains exposed to selection and survivorship bias.

## Recorded end-to-end validation

On 29 September 2026, QuantAI optimized AAPL, MSFT, NVDA, and TSLA using prices
from January 2015 through 28 September 2026. Assumptions were a 15% fixed cash
reserve, 0% annual risk-free rate, long-only weights, and a 60% maximum weight
per risky asset.

### Maximum-Sharpe portfolio

| Asset | Weight |
| --- | ---: |
| AAPL | 20.33% |
| MSFT | 6.48% |
| NVDA | 51.17% |
| TSLA | 7.01% |
| Cash | 15.00% |

- Expected annual return: 42.97%
- Annualized volatility: 31.22%
- Sharpe ratio: 1.3766

### Minimum-volatility portfolio

| Asset | Weight |
| --- | ---: |
| AAPL | 38.06% |
| MSFT | 46.94% |
| NVDA | 0.00% |
| TSLA | 0.00% |
| Cash | 15.00% |

- Expected annual return: 22.18%
- Annualized volatility: 21.50%
- Sharpe ratio: 1.0316

### One-year simulation

The maximum-Sharpe portfolio was simulated from an initial value of $100,000
using 10,000 paths and seed 42.

| Scenario | Terminal value |
| --- | ---: |
| Worst Case (P5) | $81,185 |
| Average Case | $143,404 |
| Best Case (P95) | $228,447 |

The simulated probability of finishing below the initial value was 16.02%.
Results depend directly on the high historical sample-return estimates and the
GBM assumptions described above.

### Walk-forward study

On 30 September 2026, the dashboard was validated with the same universe and
constraints, a 756-day trailing estimation window, 63-day rebalance interval,
10 bps proportional cost, and $100,000 initial value. The out-of-sample path ran
from 3 January 2018 through 29 September 2026 and contained 35 rebalances.

| Metric | Strategy | SPY benchmark |
| --- | ---: | ---: |
| CAGR | 32.10% | 14.39% |
| Maximum drawdown | -55.67% | Returned in the API path |
| Sharpe ratio | 1.026 | Returned in the API summary |

Modeled cumulative trading cost was $2,190. The large performance difference is
descriptive evidence for this chosen universe and period, not a causal claim or
an expectation of future outperformance.

With a 63-trading-day rolling risk window, the same run produced a 1.499 Sortino
ratio, 22.04% downside deviation, 1.267 beta, 0.748 correlation with SPY, 21.98%
tracking error, and 0.809 information ratio. The strategy's longest underwater
period was 421 trading days versus 488 for SPY. These values summarize this
realized hypothetical path and should not be treated as stable population
parameters.

The default 3-by-3 grid used 252-, 504-, and 756-day lookbacks with 21-, 63-,
and 126-day rebalance intervals. Across the common 3 January 2018 to 29 September
2026 period, CAGR ranged from 32.10% to 40.43%, the median CAGR was 35.40%, the
median Sharpe ratio was 1.078, and the worst maximum drawdown was -56.60%. All
nine scenarios exceeded the 14.39% SPY CAGR. This result remains strongly
conditioned on a hindsight-selected universe of surviving large-cap stocks.
