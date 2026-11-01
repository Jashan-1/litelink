# LiteLink

A phishing-aware URL shortener. LiteLink checks each destination before its short link goes live, and gives visitors an explicit warning when it cannot confirm a destination is safe.

**Status:** early. Shortening, Google sign-in, the scan queue and the safe fetcher work. The scanner itself is a stub that allows everything, so sign-in is limited to `ALLOWED_EMAILS` until the real one ships.

## How it works

```
Browser -> Next.js frontend -> FastAPI (OAuth, API, redirects) -> Postgres <- scan worker
```

The Next.js application lives in [`frontend/`](frontend/) so the product UI is independent of the FastAPI backend. In development, Next proxies API, authentication, and redirect requests to FastAPI; this keeps the browser on one origin and allows the existing session cookie and Google OAuth flow to work unchanged.

A new link starts as `pending`. The worker takes it from a queue in Postgres (`FOR UPDATE SKIP LOCKED`), scans it, and sets the status. Visitors see:

| Status | Visitor sees |
|---|---|
| `active` | A 302 redirect to the target |
| `pending` | A "checking this link" page that refreshes |
| `review` | A warning with a "continue anyway" link |
| `blocked` | A block page with the reasons |
| `disabled` | A 404 |

If a scan keeps failing, the link goes to `review`, never `active`.

## Run it locally

You need Docker.

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, SESSION_SECRET and the Google values
docker compose up --build
```

FastAPI is available at http://localhost:8000. Its built-in HTML pages are useful as a fallback; use the Next.js app below for the product interface.

## Frontend

The frontend is a responsive single-page Next.js experience with:

- A product landing page that explains the scan flow.
- Google sign-in that redirects through the existing FastAPI OAuth route.
- A signed-in workspace for creating, copying, and checking recent links.
- Public pending, review, blocked, and missing-link states.

Start the FastAPI stack first, then run the frontend in a second terminal:

```bash
# terminal 1, from the repository root
cp .env.example .env
# Set BASE_URL=http://localhost:3000, POSTGRES_PASSWORD, SESSION_SECRET,
# GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and ALLOWED_EMAILS.
docker compose up --build

# terminal 2
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. In Google Cloud Console, add `http://localhost:3000/auth/callback` as an authorized redirect URI.

The development proxy defaults to `http://localhost:8000`. To use a backend at another address, set `LITELINK_API_ORIGIN` before starting Next:

```bash
LITELINK_API_ORIGIN=http://localhost:8001 npm run dev
```

### Frontend routes

| Browser route | Purpose |
|---|---|
| `/` | Landing page or the signed-in workspace |
| `/login` | Proxied to FastAPI to begin Google OAuth |
| `/auth/callback` | Proxied OAuth callback; returns to the frontend root |
| `/:slug` | Public link status page; active links continue through `/go/:slug` |

Build a production frontend bundle with `cd frontend && npm run build`.

## Tests

The tests use a real Postgres database and wipe it, so its name must contain `test`.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
createdb litelink_test
TEST_DATABASE_URL=postgresql+psycopg://localhost/litelink_test .venv/bin/python -m pytest
```

## Deploy

On a VPS with Docker, point your domain at the server, then set these in `.env`:

- `BASE_URL=https://your-domain`
- `LITELINK_DOMAIN=your-domain`

Run `docker compose up -d --build`. Caddy gets the certificate on its own.

The current Docker Compose file deploys FastAPI, Postgres, the worker, and Caddy. Before using the separate Next.js frontend in production, host the built frontend at the public domain and route `/api`, `/login`, `/logout`, `/auth/*`, and `/go/*` to FastAPI—the same routing arrangement as `frontend/next.config.ts`.

## Collect eval data

Phishing pages disappear quickly, so snapshot them hourly from the start. On the server, add this cron job, using your repo's path:

```
0 * * * * cd /path/to/litelink && docker compose exec -T worker python -m evals.collect
```

Snapshots go to `evals/data`, which is ignored by git because it holds live phishing HTML. Reading a sample needs a shell in the `worker` container.
