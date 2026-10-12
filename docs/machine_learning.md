# Machine-Learning Return Experiment

## Research question

The module asks whether a small set of information available at the close of
day *t* contains out-of-sample information about NVDA's simple adjusted-price
return over the next five trading days. It is a controlled model-comparison
exercise, not a claim that market returns can be predicted reliably.

The target is:

```text
y(t) = adjusted_close(t + 5) / adjusted_close(t) - 1
```

## Features

The initial experiment uses 15 price, volume, and technical features:

- 1-, 5-, and 21-day trailing returns;
- one-day volume change and a 21-day log-volume z-score;
- price gaps relative to 10-, 20-, and 50-day moving averages;
- 14-day RSI, scaled to 0-1;
- price-normalized MACD, signal, and histogram;
- 21-day annualized realized volatility;
- intraday high-low range and open-to-adjusted-close return.

Every feature uses only observations at or before its prediction date. The last
five price rows have no observable target and are removed.

### Fundamental-data policy

The factor module's current PE, PB, EV/EBITDA, ROE, margin, and leverage
snapshot is deliberately excluded from the historical prediction experiment.
Backfilling today's ratios to 2015 would create severe look-ahead bias.

`build_ml_dataset` can accept optional fundamental history only when every row
has a real availability date. The implementation carries each release forward
from that date and never backward. This allows a future institutional
point-in-time dataset to be integrated without changing the feature contract.

## Experimental design

Observations are sorted chronologically and never shuffled across time. The
default split is 60% train, 20% validation, and 20% test. Five observations are
purged immediately before both validation and test boundaries so a five-day
training or validation label cannot extend into the following partition.

For the run retrieved on 29 September 2026:

| Partition | Observations | Start | End |
| --- | ---: | --- | --- |
| Train | 1,733 | 2015-03-16 | 2022-01-28 |
| Validation | 574 | 2022-02-07 | 2024-05-20 |
| Test | 580 | 2024-05-29 | 2026-09-21 |

The LSTM requires a 30-day sequence within each partition. Consequently, all
reported models are compared on the same 551 test dates from 11 July 2024
through 21 September 2026. This conservative choice does not borrow sequence
context across partition boundaries.

## Models

Four estimators provide an interpretable progression:

1. **Zero-return baseline** predicts zero for every date and establishes a
   naive error benchmark.
2. **Linear Regression** uses ordinary least squares after fitting a
   `StandardScaler` on the training partition only.
3. **XGBoost** uses depth-three boosted regression trees, regularization,
   subsampling, and validation-set early stopping.
4. **LSTM** uses a 30-day feature sequence, one 32-unit recurrent layer, a
   linear output head, Adam optimization, and validation-loss early stopping.
   Both feature and target scaling parameters come only from training data.

Random seeds are fixed at 42 and PyTorch runs on CPU with deterministic
algorithms requested where supported.

## Metrics

- **RMSE** and **MAE** are expressed in decimal return units. Lower is better.
- **Direction Accuracy** compares the exact signs of predicted and realized
  returns. A zero prediction represents no direction rather than an up move.

## Recorded result

The 29 September 2026 run produced:

| Model | RMSE | MAE | Direction Accuracy |
| --- | ---: | ---: | ---: |
| LSTM | 0.06148 | 0.04779 | 56.08% |
| Linear Regression | 0.06163 | **0.04778** | 55.54% |
| XGBoost | 0.06197 | 0.04797 | 56.08% |
| Zero-Return Baseline | 0.06203 | 0.04807 | 0.00% |

The LSTM had the lowest RMSE, while Linear Regression had the lowest MAE. The
improvements over the zero-return error baseline were small. Equal directional
accuracy across the LSTM and XGBoost does not imply equal forecasts or
economic value. No transaction-cost or statistical-significance claim is made.

## Reproduction

```bash
python scripts/run_ml_experiment.py NVDA --lstm-epochs 25 --seed 42
```

The command writes detailed metadata and daily predictions to
`artifacts/analysis/ml_nvda_report.json` and a self-contained interactive chart
to `outputs/ml_model_comparison.html`.

## Limitations

- A single security and one terminal holdout period do not establish
  generalization across assets or regimes.
- Five-day targets overlap, so adjacent test errors are serially dependent.
- Hyperparameters are illustrative rather than exhaustively tuned.
- Corporate-action-adjusted close is vendor supplied, and Yahoo Finance is not
  an institutional point-in-time database.
- The experiment excludes transaction costs, market impact, latency, taxes,
  and portfolio-construction consequences.
- RMSE, MAE, and sign accuracy alone do not demonstrate economic significance.

Future work should use walk-forward evaluation, uncertainty estimates,
multiple-testing controls, non-overlapping robustness checks, broader universes,
and properly timestamped fundamental histories.
