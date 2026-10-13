# Public deployment

QuantAI is prepared for a two-service public deployment:

- **Vercel** serves the Next.js frontend from `frontend/`.
- **Render** serves the FastAPI backend from the repository root using
  `render.yaml`.

This split preserves the existing application architecture and provides a public
URL for both services. It does not turn Yahoo Finance data into execution-grade
quotes, and every research disclaimer remains in force.

## 1. Publish the repository

Create a GitHub repository and push the project without committing secrets,
generated caches, `.env` files, or local build directories. The existing
`.gitignore` keeps those files out of version control.

## 2. Deploy the backend on Render

Create a Blueprint from the repository. Render reads `render.yaml`, installs the
lightweight Web dependencies, starts FastAPI on `$PORT`, and checks
`/api/v1/health`.

During the first Blueprint setup, set `QUANTAI_CORS_ORIGINS` to a temporary exact
HTTPS origin such as `https://placeholder.invalid`. Do not add a path or trailing
slash. After Vercel assigns the real frontend URL, replace this value with that
origin and redeploy the backend.

Do not configure `OPENAI_API_KEY` on an unauthenticated public demo. Without the
key, QuantAI intentionally uses its deterministic evidence-based explanation and
cannot incur model API charges from anonymous traffic.

Render returns a backend URL similar to:

```text
https://quantai-api.onrender.com
```

Verify these endpoints:

```text
https://quantai-api.onrender.com/api/v1/health
https://quantai-api.onrender.com/docs
```

## 3. Deploy the frontend on Vercel

Import the same GitHub repository and set the Vercel project **Root Directory**
to `frontend`. Add this production environment variable, using the actual Render
URL:

```text
NEXT_PUBLIC_API_URL=https://quantai-api.onrender.com/api/v1
```

Deploy the project. Vercel returns a public frontend URL similar to:

```text
https://quantai-dashboard.vercel.app
```

## 4. Complete CORS configuration

Return to the Render service and set:

```text
QUANTAI_CORS_ORIGINS=https://quantai-dashboard.vercel.app
```

Multiple exact origins can be comma-delimited, for example a Vercel URL and a
custom domain. Saving the environment variable triggers a backend redeploy.

## 5. Production smoke test

From the public frontend, verify:

1. Market Overview displays either live or explicitly labeled cached data.
2. Stock Analysis completes for `AAPL` and `600519.SS`.
3. Portfolio Optimizer completes for `AAPL, MSFT, NVDA, TSLA`.
4. English and Chinese switching works after a page reload.
5. Browser developer tools show no CORS or mixed-content errors.

## Hosting limitations

- Free Render Web Services can spin down while idle, so the first request after
  inactivity can be slower.
- The Blueprint sets `autoDeployTrigger: commit`, so pushes to the linked `main`
  branch deploy the backend without a separate manual Render action. Confirm the
  latest commit hash in Render after each release.
- Render's default filesystem is ephemeral. Market-data caches improve continuity
  within an instance but are lost on a restart or redeploy unless a paid persistent
  disk or external datastore is configured.
- Yahoo Finance is a research data source and can throttle or temporarily fail.
  QuantAI limits portfolio downloads to two concurrent symbols, retries live
  requests with bounded backoff, and then uses an explicitly labeled compatible
  cache snapshot when one exists.
- Public production use should add authentication, rate limiting, monitoring, and
  a managed persistent datastore before enabling paid AI explanations.
