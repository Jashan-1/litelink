# LiteLink

A URL shortener that checks each link for phishing before it goes live, with public eval numbers showing how well the scanner works.

**Status:** early. Shortening, Google sign-in, the scan queue and the safe fetcher work. The scanner itself is a stub that allows everything, so sign-in is limited to `ALLOWED_EMAILS` until the real one ships.

## How it works

```
Caddy (HTTPS) -> FastAPI (redirects, API, pages) -> Postgres <- scan worker
```

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

Open http://localhost:8000. The Google OAuth client needs `http://localhost:8000/auth/callback` as an authorized redirect URI.

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

## Collect eval data

Phishing pages disappear quickly, so snapshot them hourly from the start. On the server, add this cron job, using your repo's path:

```
0 * * * * cd /path/to/litelink && docker compose exec -T worker python -m evals.collect
```

Snapshots go to `evals/data`, which is ignored by git because it holds live phishing HTML. Reading a sample needs a shell in the `worker` container.
