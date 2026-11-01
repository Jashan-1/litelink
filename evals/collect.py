"""Snapshot fresh phishing pages before they disappear: python -m evals.collect

Run it hourly. Each URL gets one JSON file in evals/data, including failures, so a
dead page isn't retried. OpenPhish is only the label source. Keep it out of the
blocklist baseline in the eval, or that baseline looks perfect by construction.
"""
import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path

import httpx

from app.scanner.ssrf import safe_fetch

logger = logging.getLogger(__name__)

FEED_URL = "https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt"
SAFE_BROWSING_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
MAX_PER_RUN = 100
CONCURRENCY = 5
DATA_DIR = Path(os.getenv("EVALS_DATA_DIR", "evals/data"))


def path_for(url: str) -> Path:
    return DATA_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


async def fetch_feed(client: httpx.AsyncClient) -> list[str]:
    response = await client.get(FEED_URL)
    response.raise_for_status()
    return [line.strip() for line in response.text.splitlines() if line.strip()]


async def safe_browsing_hits(client: httpx.AsyncClient, urls: list[str], api_key: str) -> set[str] | None:
    """URLs Safe Browsing flags right now. None means unknown, which is different from 'not flagged'."""
    if not api_key or not urls:
        return None
    payload = {
        "client": {"clientId": "litelink-evals", "clientVersion": "0.1"},
        "threatInfo": {
            "threatTypes": ["SOCIAL_ENGINEERING", "MALWARE", "UNWANTED_SOFTWARE"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url} for url in urls],
        },
    }
    try:
        response = await client.post(SAFE_BROWSING_URL, params={"key": api_key}, json=payload)
        response.raise_for_status()
    except httpx.HTTPError as error:
        # str(error) can include the request URL, and that URL holds the API key.
        logger.warning("Safe Browsing lookup failed: %s", type(error).__name__)
        return None
    return {match["threat"]["url"] for match in response.json().get("matches", [])}


async def snapshot(url: str, hits: set[str] | None) -> None:
    record = {
        "url": url,
        "source": "openphish",
        "label": "phishing",
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "safe_browsing_flagged": None if hits is None else url in hits,
    }
    try:
        page = await safe_fetch(url)
        record.update(
            final_url=page.final_url, chain=page.chain, status=page.status, truncated=page.truncated,
            html=page.body.decode("utf-8", errors="replace"),
        )
    except Exception as error:  # dead pages are the normal case here
        record["error"] = f"{type(error).__name__}: {error}"
    path_for(url).write_text(json.dumps(record))


async def collect(client: httpx.AsyncClient, api_key: str) -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    urls = [url for url in await fetch_feed(client) if not path_for(url).exists()][:MAX_PER_RUN]
    hits = await safe_browsing_hits(client, urls, api_key)
    limit = asyncio.Semaphore(CONCURRENCY)

    async def limited(url: str) -> None:
        async with limit:
            await snapshot(url, hits)

    await asyncio.gather(*(limited(url) for url in urls))
    return len(urls)


async def main() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        count = await collect(client, os.getenv("SAFE_BROWSING_API_KEY", ""))
    print(f"Saved {count} new URLs to {DATA_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
