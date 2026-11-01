import json

import httpx
import pytest

from app.scanner.ssrf import BlockedURL, Fetched
from evals import collect


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "DATA_DIR", tmp_path)
    return tmp_path


def feed_client(*urls, flagged=(), safe_browsing_status=200):
    def handler(request):
        if "safebrowsing" in request.url.host:
            matches = [{"threat": {"url": url}} for url in flagged]
            return httpx.Response(safe_browsing_status, json={"matches": matches})
        return httpx.Response(200, text="\n".join(urls) + "\n\n")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def fake_fetch(url):
    if "dead" in url:
        raise BlockedURL("gone")
    return Fetched(url, 200, b"<html>caf\xc3\xa9 \xff</html>", False, [url])


def load(url):
    return json.loads(collect.path_for(url).read_text())


async def test_saves_pages_and_records_dead_ones(data_dir, monkeypatch):
    monkeypatch.setattr(collect, "safe_fetch", fake_fetch)
    async with feed_client("https://live.test/", "https://dead.test/", flagged=["https://live.test/"]) as client:
        assert await collect.collect(client, "key") == 2

    live = load("https://live.test/")
    assert live["html"].startswith("<html>café")  # invalid bytes don't lose the snapshot
    assert (live["label"], live["safe_browsing_flagged"]) == ("phishing", True)

    dead = load("https://dead.test/")
    assert dead["safe_browsing_flagged"] is False
    assert dead["error"] == "BlockedURL: gone"


async def test_second_run_skips_saved_urls(data_dir, monkeypatch):
    monkeypatch.setattr(collect, "safe_fetch", fake_fetch)
    async with feed_client("https://live.test/", "https://dead.test/") as client:
        await collect.collect(client, "")
        assert await collect.collect(client, "") == 0


@pytest.mark.parametrize("key, status", [("", 200), ("key", 500)])
async def test_unknown_safe_browsing_result_stays_unknown(data_dir, monkeypatch, key, status):
    monkeypatch.setattr(collect, "safe_fetch", fake_fetch)
    async with feed_client("https://live.test/", safe_browsing_status=status) as client:
        await collect.collect(client, key)
    assert load("https://live.test/")["safe_browsing_flagged"] is None
