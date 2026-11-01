import os
import subprocess
import sys

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://localhost/litelink_test")
assert "test" in DATABASE_URL, "These tests wipe the database, so its name must contain 'test'."
os.environ.update(
    DATABASE_URL=DATABASE_URL, BASE_URL="https://short.test", SESSION_SECRET="test-secret",
    GOOGLE_CLIENT_ID="client-id", GOOGLE_CLIENT_SECRET="client-secret", ALLOWED_EMAILS="me@example.com",
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.auth import current_user  # noqa: E402
from app.db import Session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Builds the schema with the real migrations, so they're tested too."""
    engine = create_engine(DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


@pytest.fixture(autouse=True)
async def clean(schema):
    async with Session.begin() as session:
        await session.execute(text("TRUNCATE users, links, scan_jobs, scans RESTART IDENTITY CASCADE"))


@pytest.fixture
async def user():
    async with Session.begin() as session:
        person = User(google_sub="sub-1", email="me@example.com")
        session.add(person)
    return person


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://short.test") as test_client:
        yield test_client


@pytest.fixture
def signed_in(client, user):
    app.dependency_overrides[current_user] = lambda: user
    yield client
    app.dependency_overrides.clear()
