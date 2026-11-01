"""Settings from the environment. A missing required value stops the process at startup."""
import os
from urllib.parse import urlsplit

DATABASE_URL = os.environ["DATABASE_URL"]  # postgresql+psycopg://user:password@host/dbname
BASE_URL = os.environ["BASE_URL"].rstrip("/")  # public origin, e.g. https://litelink.dev
BASE_HOST = urlsplit(BASE_URL).hostname
SESSION_SECRET = os.environ["SESSION_SECRET"]

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
ALLOWED_EMAILS = frozenset(e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip())
