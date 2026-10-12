# Evidence-grounded AI explanations

## Purpose

The explanation module translates displayed quantitative outputs into concise
research prose. It does not calculate a new signal, predict a price, or produce
investment advice.

## Data boundary

The endpoint `GET /api/v1/stocks/{ticker}/explanation` first obtains the same
typed stock analysis used by the dashboard. Application code then creates four
evidence cards:

1. composite factor score, rank, strongest component, and weakest component;
2. geometric historical annualized return and sample dates;
3. annualized volatility and maximum drawdown;
4. one-day historical VaR and its confidence level.

The application also fixes the risk label and limitations. The model receives
no free-form browser prompt and cannot modify those fields.

## OpenAI integration

QuantAI uses the official Python SDK and Responses API. Its Pydantic
`NarrativeDraft` schema restricts the generated fields to a summary and two to
four observations. The request sets `store=False`. Official OpenAI guidance
recommends the Responses API for direct text generation and supports native
Pydantic schemas through Structured Outputs:

- <https://developers.openai.com/api/docs/guides/text>
- <https://developers.openai.com/api/docs/guides/structured-outputs>
- <https://developers.openai.com/api/docs/libraries>

Configure the backend process with:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-6-luna
```

Set these variables in the process environment before starting FastAPI. The
repository's `.env.example` is a configuration template and is not loaded
automatically.

The model is configurable because account access and model availability can
vary. The API key must never use a `NEXT_PUBLIC_` name or enter frontend code.

## Failure behavior

Missing credentials, an unavailable provider, refusal, or an unparsable result
all select the deterministic narrative. The response always discloses
`source`, `model`, and `provider_message`; provider exception details and
credentials are not returned to the browser.

## Verification

Unit tests cover:

- deterministic output when the key is missing;
- the Structured Outputs request boundary and disabled storage;
- safe fallback without leaking provider exception details;
- the typed FastAPI response contract.

The generated prose remains non-deterministic when OpenAI is enabled. A future
evaluation suite should check factual consistency, prohibited recommendation
language, stability across prompt revisions, and multilingual quality.
