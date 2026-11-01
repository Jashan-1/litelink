from unittest.mock import AsyncMock

import pytest
from authlib.integrations.starlette_client import OAuthError
from sqlalchemy import select

from app import auth
from app.db import Session
from app.models import User


def google_returns(monkeypatch, **claims):
    info = {"sub": "google-1", "email": "Me@Example.com", "email_verified": True, **claims}
    mock = AsyncMock(return_value={"userinfo": info})
    monkeypatch.setattr(auth.oauth.google, "authorize_access_token", mock)


async def test_sign_in_creates_a_session_and_user(client, monkeypatch):
    google_returns(monkeypatch)
    response = await client.get("/auth/callback")
    assert (response.status_code, response.headers["location"]) == (303, "/")
    assert "me@example.com" in (await client.get("/")).text
    assert (await client.get("/api/links")).status_code == 200


async def test_second_sign_in_reuses_the_user_and_updates_the_email(client, monkeypatch):
    google_returns(monkeypatch)
    await client.get("/auth/callback")
    google_returns(monkeypatch, email="me@example.com", name="ignored")
    await client.get("/auth/callback")
    async with Session() as session:
        assert len(list(await session.scalars(select(User)))) == 1


@pytest.mark.parametrize("claims", [{"email_verified": False}, {"email": "stranger@example.com"}])
async def test_unverified_or_unlisted_accounts_are_refused(client, monkeypatch, claims):
    google_returns(monkeypatch, **claims)
    assert (await client.get("/auth/callback")).status_code == 403
    assert (await client.get("/api/links")).status_code == 401


async def test_failed_google_exchange_is_a_400(client, monkeypatch):
    monkeypatch.setattr(auth.oauth.google, "authorize_access_token", AsyncMock(side_effect=OAuthError("mismatching_state")))
    assert (await client.get("/auth/callback")).status_code == 400


async def test_logout_ends_the_session(client, monkeypatch):
    google_returns(monkeypatch)
    await client.get("/auth/callback")
    assert (await client.post("/logout")).status_code == 303
    assert (await client.get("/api/links")).status_code == 401


async def test_forged_cookie_is_ignored(client):
    client.cookies.set("litelink_session", "eyJ1c2VyX2lkIjogMX0=.forged.signature")
    assert (await client.get("/api/links")).status_code == 401
