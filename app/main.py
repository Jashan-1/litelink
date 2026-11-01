import secrets
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, pages
from .db import get_session
from .models import Link, Scan, ScanJob, User

# No look-alike characters (0/O, 1/l/I), since people retype these.
SLUG_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
# shortcut: every fixed route is under 7 characters so a slug can't shadow one, add a reserved list with custom slugs
SLUG_LENGTH = 7
SLUG_ATTEMPTS = 5
MAX_URL_LENGTH = 2048
RECENT_LINKS = 50

app = FastAPI(title="LiteLink")
app.add_middleware(
    SessionMiddleware, secret_key=config.SESSION_SECRET, session_cookie="litelink_session",
    max_age=7 * 24 * 3600, same_site="lax", https_only=config.BASE_URL.startswith("https://"),
)
app.include_router(auth.router)


class NewLink(BaseModel):
    target_url: str


class LinkOut(BaseModel):
    slug: str
    short_url: str
    target_url: str
    status: str


def new_slug() -> str:
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(SLUG_LENGTH))


def url_problem(url: str) -> str | None:
    if not 1 <= len(url) <= MAX_URL_LENGTH:
        return f"URLs can be up to {MAX_URL_LENGTH} characters."
    # Browsers read "\" as "/" but urlsplit doesn't, so the two would disagree about the host.
    if "\\" in url or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        return "URLs can't contain spaces, backslashes or control characters."
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "That URL isn't valid."
    if parts.scheme not in ("http", "https") or not host:
        return "Use a full http:// or https:// URL."
    if host == config.BASE_HOST:
        return "That's already a short link."
    return None


def to_output(link: Link) -> LinkOut:
    return LinkOut(
        slug=link.slug, short_url=f"{config.BASE_URL}/{link.slug}", target_url=link.target_url, status=link.status
    )


async def recent_links(session: AsyncSession, user: User) -> list[Link]:
    query = select(Link).where(Link.owner_id == user.id).order_by(Link.id.desc()).limit(RECENT_LINKS)
    return list(await session.scalars(query))


@app.get("/")
async def home(user: User | None = Depends(auth.optional_user), session: AsyncSession = Depends(get_session)):
    if user is None:
        return pages.signed_out()
    return pages.home(user, await recent_links(session, user), config.BASE_URL)


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/links", status_code=201)
async def create_link(
    body: NewLink, user: User = Depends(auth.current_user), session: AsyncSession = Depends(get_session)
) -> LinkOut:
    problem = url_problem(body.target_url)
    if problem:
        raise HTTPException(422, problem)
    for _ in range(SLUG_ATTEMPTS):
        statement = (
            insert(Link)
            .values(slug=new_slug(), owner_id=user.id, target_url=body.target_url)
            .on_conflict_do_nothing(index_elements=["slug"])
            .returning(Link.id)
        )
        link_id = await session.scalar(statement)
        if link_id is not None:
            # Same transaction as the link, so a pending link always has a job.
            session.add(ScanJob(link_id=link_id, target_url=body.target_url))
            await session.commit()
            return to_output(await session.get_one(Link, link_id))
    raise HTTPException(503, "Couldn't allocate a short link. Try again.")


@app.get("/api/links")
async def list_links(
    user: User = Depends(auth.current_user), session: AsyncSession = Depends(get_session)
) -> list[LinkOut]:
    return [to_output(link) for link in await recent_links(session, user)]


# Must stay last: it matches every other single-segment path.
@app.api_route("/{slug}", methods=["GET", "HEAD"], include_in_schema=False)
async def follow(slug: str, session: AsyncSession = Depends(get_session)):
    link = await session.scalar(select(Link).where(Link.slug == slug))
    if link is None or link.status == "disabled":
        return pages.not_found()
    if link.status == "active":
        return RedirectResponse(link.target_url, status_code=302, headers=pages.NO_INDEX)
    if link.status == "pending":
        return pages.pending()
    if link.status == "review":
        return pages.review(link.target_url)
    latest = await session.scalar(select(Scan).where(Scan.link_id == link.id).order_by(Scan.id.desc()).limit(1))
    return pages.blocked(latest.reasons if latest else [])
