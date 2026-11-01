"""Server-rendered HTML. Everything that comes from a user or a scan goes through e()."""
from html import escape as e
from typing import Sequence

from fastapi.responses import HTMLResponse

from .models import Link, User

STYLE = """
body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}
input{font:inherit;padding:.5rem;width:100%;box-sizing:border-box;margin-bottom:.5rem}
button{font:inherit;padding:.5rem 1rem;cursor:pointer}
table{width:100%;border-collapse:collapse;margin-top:1.5rem}
td{padding:.4rem .4rem .4rem 0;border-top:1px solid #ddd;word-break:break-all;vertical-align:top}
.url{word-break:break-all;font-family:ui-monospace,monospace}
"""
NO_INDEX = {"X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def page(title: str, body: str, *, status: int = 200, head: str = "") -> HTMLResponse:
    html = (
        f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">{head}'
        f"<title>{e(title)} · LiteLink</title><style>{STYLE}</style><body>{body}</body></html>"
    )
    return HTMLResponse(html, status_code=status, headers=NO_INDEX)


def not_found() -> HTMLResponse:
    return page("Not found", "<h1>Link not found</h1>", status=404)


def pending() -> HTMLResponse:
    return page(
        "Checking this link",
        "<h1>Checking this link</h1><p>This usually takes a few seconds. The page will refresh by itself.</p>",
        head='<meta http-equiv="refresh" content="3">',
    )


def review(target_url: str) -> HTMLResponse:
    # The target was validated as http(s) on creation, so it is safe as an href once escaped.
    return page("Check before you continue", f"""
<h1>Check before you continue</h1>
<p>We couldn't confirm this link is safe. Only continue if you trust whoever sent it.</p>
<p class="url">{e(target_url)}</p>
<p><a href="{e(target_url)}" rel="noopener noreferrer nofollow">Continue anyway</a></p>""")


def blocked(reasons: Sequence[str]) -> HTMLResponse:
    items = "".join(f"<li>{e(reason)}</li>" for reason in reasons)
    return page("Link blocked", f"<h1>This link was blocked</h1><p>It looks unsafe.</p><ul>{items}</ul>", status=403)


def signed_out() -> HTMLResponse:
    return page("Short links, checked for phishing", """
<h1>LiteLink</h1>
<p>Short links, checked for phishing before they go live.</p>
<p><a href="/login">Sign in with Google</a></p>""")


def home(user: User, links: Sequence[Link], base_url: str) -> HTMLResponse:
    rows = "".join(
        f'<tr><td><a href="/{e(link.slug)}">{e(base_url)}/{e(link.slug)}</a></td>'
        f"<td>{e(link.target_url)}</td><td>{e(link.status)}</td></tr>"
        for link in links
    )
    return page("Your links", f"""
<h1>LiteLink</h1>
<p>{e(user.email)}</p>
<form id="new"><label for="target">Long URL</label>
<input id="target" type="url" required placeholder="https://example.com/a/long/path">
<button>Shorten</button></form>
<p id="error" role="alert"></p>
<table>{rows}</table>
<form method="post" action="/logout"><p><button>Sign out</button></p></form>
<script>
document.getElementById("new").addEventListener("submit", async (event) => {{
  event.preventDefault();
  const response = await fetch("/api/links", {{
    method: "POST", headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{target_url: document.getElementById("target").value}}),
  }});
  if (response.ok) return location.reload();
  const body = await response.json();
  document.getElementById("error").textContent = typeof body.detail === "string" ? body.detail : "That URL isn't valid.";
}});
</script>""")
