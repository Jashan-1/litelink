from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from . import config
from .db import get_session
from .models import User

router = APIRouter()
oauth = OAuth()
oauth.register(
    "google",
    client_id=config.GOOGLE_CLIENT_ID,
    client_secret=config.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email"},
)


async def optional_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
    user_id = request.session.get("user_id")
    return await session.get(User, user_id) if user_id else None


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in first.")
    return user


@router.get("/login")
async def login(request: Request):
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not configured.")
    return await oauth.google.authorize_redirect(request, f"{config.BASE_URL}/auth/callback")


@router.get("/auth/callback")
async def callback(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        raise HTTPException(400, "Sign-in failed. Try again.")
    info = token["userinfo"]
    email = info["email"].lower()
    # shortcut: fails closed for everyone not listed, drop the list once the real scanner replaces the stub
    if not info.get("email_verified") or email not in config.ALLOWED_EMAILS:
        raise HTTPException(403, "This account can't sign in yet.")
    statement = insert(User).values(google_sub=info["sub"], email=email)
    statement = statement.on_conflict_do_update(index_elements=["google_sub"], set_={"email": email})
    user_id = await session.scalar(statement.returning(User.id))
    await session.commit()
    request.session.clear()  # a fresh session, so nothing from before sign-in carries over
    request.session["user_id"] = user_id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
