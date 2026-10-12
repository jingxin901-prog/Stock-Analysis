# Historical Market-Data Validation

## Purpose

This validation checks whether the live Yahoo Finance adapter satisfies the
internal QuantAI data contract before financial metrics are calculated. It is a
pipeline-quality check, not an independent audit of Yahoo Finance prices.

## Reproduce

From an installed project environment with internet access:

```bash
python scripts/validate_market_data.py
```

The default universe is AAPL, MSFT, NVDA, TSLA, AMZN, and GOOGL, with a requested
start date of 2015-01-01. The script writes its detailed JSON output to
`artifacts/validation/market_data_validation.json`. That generated artifact is
excluded from Git because results vary with retrieval time.

## Validation criteria

Each standardized DataFrame must satisfy all of the following:

1. It is non-empty and uses the documented column contract.
2. Its ticker column is consistent with the request.
3. It has an ascending, unique `DatetimeIndex`.
4. It contains no missing values after normalization.
5. Price fields are numeric and volume is a nonnegative integer.
6. High and low values enclose open and close values for every row.
7. The first observation is within ten calendar days of the requested start.
8. The latest observation is no more than fourteen calendar days old.

## Recorded run

- Validation time: 2026-09-29 UTC
- Python: 3.12.14
- pandas: 3.0.6
- yfinance: 1.7.0
- Result: 6 of 6 symbols passed

| Ticker | Rows | First observation | Last observation | Missing cells | Duplicate dates | Status |
| --- | ---: | --- | --- | ---: | ---: | --- |
| AAPL | 2,951 | 2015-01-02 | 2026-09-28 | 0 | 0 | Passed |
| MSFT | 2,951 | 2015-01-02 | 2026-09-28 | 0 | 0 | Passed |
| NVDA | 2,951 | 2015-01-02 | 2026-09-28 | 0 | 0 | Passed |
| TSLA | 2,951 | 2015-01-02 | 2026-09-28 | 0 | 0 | Passed |
| AMZN | 2,951 | 2015-01-02 | 2026-09-28 | 0 | 0 | Passed |
| GOOGL | 2,951 | 2015-01-02 | 2026-09-28 | 0 | 0 | Passed |

## Interpretation and limitations

The run demonstrates that the adapter returned complete, recent, internally
consistent daily records for the sample universe under the specified contract.
It does not prove that vendor prices are error-free or point-in-time accurate.
It also does not test delisted securities, ticker changes, non-US calendars,
corporate-action revision history, or survivorship bias. Those remain explicit
limitations of subsequent empirical work.
