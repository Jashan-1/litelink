import pytest
from sqlalchemy import func, select, update

from app.db import Session
from app.main import SLUG_ALPHABET, SLUG_LENGTH, app, new_slug
from app.models import Link, Scan, ScanJob, User


async def create(client, url="https://example.com/long?a=1"):
    return await client.post("/api/links", json={"target_url": url})


async def set_status(slug, status):
    async with Session.begin() as session:
        await session.execute(update(Link).where(Link.slug == slug).values(status=status))


def test_slugs_use_the_safe_alphabet():
    slugs = {new_slug() for _ in range(1000)}
    assert len(slugs) == 1000
    assert all(len(slug) == SLUG_LENGTH and set(slug) <= set(SLUG_ALPHABET) for slug in slugs)


def test_no_fixed_route_can_be_shadowed_by_a_slug():
    segments = {path.split("/")[1] for path in app.openapi()["paths"]} | {"docs", "redoc", "openapi.json"}
    assert len(segments) > 5  # api, auth, health, login, logout and the docs routes
    assert all(len(segment) != SLUG_LENGTH for segment in segments)


async def test_creating_a_link_needs_sign_in(client):
    assert (await create(client)).status_code == 401


async def test_create_starts_pending_with_a_queued_job(signed_in):
    response = await create(signed_in)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["short_url"] == f"https://short.test/{body['slug']}"
    async with Session() as session:
        job = await session.scalar(select(ScanJob))
    assert (job.status, job.target_url) == ("queued", "https://example.com/long?a=1")


@pytest.mark.parametrize("url", [
    "", "example.com", "ftp://example.com/", "javascript:alert(1)", "data:text/html,x", "https://",
    "https://exa mple.com/", "https://evil.test\\@example.com/", "https://example.com/\n", "https://[bad/",
    "https://short.test/abc", "https://example.com/" + "a" * 2048,
])
async def test_bad_urls_are_rejected_and_create_nothing(signed_in, url):
    assert (await create(signed_in, url)).status_code == 422
    async with Session() as session:
        assert await session.scalar(select(func.count()).select_from(Link)) == 0


async def test_slug_collision_retries(signed_in, monkeypatch):
    first = (await create(signed_in)).json()["slug"]
    slugs = iter([first, "fresh22"])
    monkeypatch.setattr("app.main.new_slug", lambda: next(slugs))
    assert (await create(signed_in)).json()["slug"] == "fresh22"


async def test_active_link_redirects(signed_in):
    slug = (await create(signed_in)).json()["slug"]
    await set_status(slug, "active")
    response = await signed_in.get(f"/{slug}")
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/long?a=1"
    assert response.headers["cache-control"] == "no-store"
    assert (await signed_in.head(f"/{slug}")).status_code == 302


async def test_pending_link_shows_a_refreshing_page_and_never_the_target(signed_in):
    slug = (await create(signed_in)).json()["slug"]
    response = await signed_in.get(f"/{slug}")
    assert response.status_code == 200
    assert 'http-equiv="refresh"' in response.text
    assert "example.com" not in response.text


async def test_review_link_warns_and_escapes_the_target(signed_in):
    slug = (await create(signed_in, 'https://example.com/"><script>alert(1)</script>')).json()["slug"]
    await set_status(slug, "review")
    response = await signed_in.get(f"/{slug}")
    assert "Continue anyway" in response.text
    assert "<script>alert" not in response.text


async def test_blocked_link_shows_escaped_reasons_and_never_the_target(signed_in):
    created = (await create(signed_in)).json()
    await set_status(created["slug"], "blocked")
    async with Session.begin() as session:
        link = await session.scalar(select(Link))
        session.add(Scan(link_id=link.id, target_url=link.target_url, verdict="block", reasons=["<b>fake bank</b>"]))
    response = await signed_in.get(f"/{created['slug']}")
    assert response.status_code == 403
    assert "&lt;b&gt;fake bank" in response.text
    assert "example.com" not in response.text


async def test_disabled_and_unknown_links_are_404(signed_in):
    slug = (await create(signed_in)).json()["slug"]
    await set_status(slug, "disabled")
    assert (await signed_in.get(f"/{slug}")).status_code == 404
    assert (await signed_in.get("/nothere")).status_code == 404


async def test_people_only_see_their_own_links(signed_in, user):
    await create(signed_in)
    async with Session.begin() as session:
        other = User(google_sub="sub-2", email="other@example.com")
        session.add(other)
        await session.flush()
        session.add(Link(slug="others1", owner_id=other.id, target_url="https://other.example/"))
    listed = (await signed_in.get("/api/links")).json()
    assert [link["target_url"] for link in listed] == ["https://example.com/long?a=1"]


async def test_health_and_signed_out_home(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert "Sign in with Google" in (await client.get("/")).text
