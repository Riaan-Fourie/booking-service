"""All API routes for the booking service."""

import asyncio
import hmac
import json
import logging
import re
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import httpx
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.config import config
from app.cal_client import get_available_slots, create_booking, get_event_type, update_event_type_title
from app.og_image import generate_og_image, get_static_og_image

logger = logging.getLogger("booking.routes")

router = APIRouter()

# ── Crawler detection for fast OG responses ─────────────────────
_CRAWLER_KEYWORDS = (
    "whatsapp", "telegrambot", "facebookexternalhit", "facebot",
    "linkedinbot", "twitterbot", "slackbot", "discordbot",
    "googlebot", "bingbot", "applebot", "iframely", "embedly",
    "preview", "crawler", "spider", "bot/",
)


def _is_crawler(request: Request) -> bool:
    """Check if the request is from a social media or search crawler."""
    ua = (request.headers.get("user-agent") or "").lower()
    return any(kw in ua for kw in _CRAWLER_KEYWORDS)


# ── Rate limiter (in-memory, per-IP) ────────────────────────────
_rate_limits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str, window: int = 300, max_attempts: int = 5) -> bool:
    """Return True if the client is within rate limits, False if blocked."""
    now = time.time()
    key_attempts = _rate_limits[client_ip]
    _rate_limits[client_ip] = [t for t in key_attempts if now - t < window]
    if len(_rate_limits[client_ip]) >= max_attempts:
        return False
    _rate_limits[client_ip].append(now)
    return True

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "booking.html"
STATIC_DIR = Path(__file__).parent.parent / "static"

def _get_template() -> str:
    """Load the HTML template (re-reads each time for dev, file is tiny)."""
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _error_page(title: str, subtitle: str) -> str:
    """Generate a styled error page matching the booking page aesthetic."""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>{_escape_html(title)} · {_escape_html(config.OWNER_NAME)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;font-family:'Inter',-apple-system,sans-serif;color:#fff}}
.bg{{position:fixed;inset:0;background-image:url('/book/static/duckweed-farm.webp');background-size:cover;background-position:center 35%;z-index:0}}
.wrap{{display:flex;align-items:flex-end;justify-content:center;padding:16px 16px 20vh;position:relative;z-index:2;min-height:100vh;text-align:center}}
.inner{{max-width:400px}}
.icon{{width:52px;height:52px;border-radius:50%;background:rgba(255,255,255,.08);border:2px solid rgba(255,255,255,.7);display:flex;align-items:center;justify-content:center;margin:0 auto 20px}}
h1{{font-size:26px;font-weight:700;letter-spacing:-.5px;margin-bottom:8px;text-shadow:0 2px 20px rgba(0,0,0,.5)}}
p{{font-size:14px;color:rgba(255,255,255,.9);line-height:1.6;text-shadow:0 2px 12px rgba(0,0,0,.5)}}
</style></head><body>
<div class="bg"></div>
<div class="wrap"><div class="inner">
<div class="icon">
<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.85)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
</div>
<h1>{_escape_html(title)}</h1>
<p>{_escape_html(subtitle)}</p>
</div></div>
</body></html>"""


@contextmanager
def _get_db():
    """Get a database connection with guaranteed cleanup."""
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def _slugify(name: str) -> str:
    """Convert a name to a clean URL slug. Appends suffix only on collision."""
    transliterations = {
        "ü": "ue", "ö": "oe", "ä": "ae", "ß": "ss",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "á": "a", "à": "a", "â": "a", "ã": "a",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "ô": "o", "õ": "o",
        "ú": "u", "ù": "u", "û": "u",
        "ñ": "n", "ç": "c",
    }
    slug = name.lower().strip()
    for char, replacement in transliterations.items():
        slug = slug.replace(char, replacement)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")

    # Check for collision, append short suffix only if needed
    candidate = slug
    try:
        with _get_db() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM booking_invites WHERE slug = %s", (candidate,))
            if cur.fetchone():
                candidate = f"{slug}-{uuid.uuid4().hex[:4]}"
    except Exception:
        # If DB check fails, always add suffix to be safe
        candidate = f"{slug}-{uuid.uuid4().hex[:4]}"

    return candidate


def _require_api_key(request: Request) -> None:
    """Check API key for admin endpoints."""
    if not config.BOOKING_API_KEY:
        raise HTTPException(status_code=503, detail="API key not configured")
    key = request.headers.get("X-API-Key", "")
    if key != config.BOOKING_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Pydantic models ─────────────────────────────────────────────


@router.get("/robots.txt")
async def robots_txt():
    """Block all crawlers from indexing booking pages."""
    return Response(
        content="User-agent: *\nDisallow: /book/\nDisallow: /api/\n",
        media_type="text/plain",
    )


class InviteCreate(BaseModel):
    recipient_name: str
    recipient_first_name: str
    recipient_email: Optional[str] = None
    contact_id: Optional[str] = None
    greeting: str = "A note for"
    context_quote: Optional[str] = None
    closing: str = "Looking forward to the conversation."
    cal_link: Optional[str] = None
    duration_minutes: Optional[int] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    expires_days: Optional[int] = Field(default=30, description="Days until invite expires")
    meeting_type: Optional[str] = Field(default=None, description="Meeting type: discovery_call, coffee_chat")


VALID_STATUSES = {"active", "booked", "expired", "cancelled"}


class InviteUpdate(BaseModel):
    status: Optional[str] = None
    context_quote: Optional[str] = None
    closing: Optional[str] = None
    cal_link: Optional[str] = None
    meeting_type: Optional[str] = None


class AdminLogin(BaseModel):
    password: str


# ── Public endpoints ─────────────────────────────────────────────

ADMIN_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "admin.html"


@router.get("/book/admin", response_class=HTMLResponse)
async def serve_admin_page():
    """Serve the admin dashboard. Login form handles auth."""
    return HTMLResponse(content=ADMIN_TEMPLATE_PATH.read_text(encoding="utf-8"))


@router.post("/api/v1/admin/auth")
async def admin_login(login: AdminLogin, request: Request):
    """Exchange a memorable password for the API key (rate-limited)."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 5 minutes.")
    if not config.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin password not configured")
    if not hmac.compare_digest(login.password.encode(), config.ADMIN_PASSWORD.encode()):
        raise HTTPException(status_code=401, detail="Wrong password")
    return JSONResponse(content={"api_key": config.BOOKING_API_KEY})


@router.get("/book/og/{slug}.jpg")
async def serve_og_image(slug: str):
    """Serve a dynamic OG image (JPEG) for link previews. Must be before /book/{slug}."""
    # Generic page OG image (no personalization)
    if slug == "_generic":
        try:
            img_bytes = generate_og_image("", theme="duckweed")
        except Exception:
            img_bytes = get_static_og_image(theme="duckweed")
        return Response(
            content=img_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    try:
        with _get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT recipient_name, meeting_type FROM booking_invites WHERE slug = %s", (slug,))
            row = cur.fetchone()
    except Exception:
        logger.exception("DB error fetching invite for OG image")
        return Response(content=get_static_og_image(), media_type="image/jpeg")

    if not row:
        return Response(content=get_static_og_image(), media_type="image/jpeg")

    theme = "coffee" if row.get("meeting_type") == "coffee_chat" else "duckweed"
    try:
        img_bytes = generate_og_image(row["recipient_name"], theme=theme)
    except Exception:
        logger.exception("Failed to generate OG image for %s", slug)
        img_bytes = get_static_og_image(theme=theme)

    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/book/static/{filename}")
async def serve_static(filename: str):
    """Serve static files (background image, etc.)."""
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = STATIC_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    ext = filepath.suffix.lower()
    media_type = media_types.get(ext, "application/octet-stream")

    return Response(
        content=filepath.read_bytes(),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/book", response_class=HTMLResponse)
async def serve_generic_booking_page(request: Request):
    """Serve a generic (non-personalized) booking page for email signatures etc."""
    # Track views on the _generic sentinel row
    try:
        with _get_db() as conn_gv, conn_gv.cursor() as cur_gv:
            cur_gv.execute(
                "UPDATE booking_invites SET view_count = COALESCE(view_count, 0) + 1 WHERE slug = '_generic'"
            )
            conn_gv.commit()
    except Exception:
        logger.warning("Failed to increment generic view_count")

    template = _get_template()
    mt_config = config.MEETING_TYPES["none"]
    cal_link = f"{config.CAL_USERNAME}/{mt_config['slug']}"
    base_url = config.BASE_URL

    html = template
    html = html.replace("{{SLUG}}", "")
    html = html.replace("{{BASE_URL}}", base_url)
    html = html.replace("{{THEME}}", "duckweed")
    html = html.replace("{{BG_IMAGE}}", f"{base_url}/book/static/duckweed-farm.webp")
    html = html.replace("{{OG_TITLE}}", f"Book a call with {config.OWNER_NAME}")
    html = html.replace("{{OG_DESCRIPTION}}", "Pick a time that works and let&#x27;s connect.")
    html = html.replace("{{OG_IMAGE_URL}}", f"{base_url}/book/og/_generic.jpg")
    html = html.replace("{{RECIPIENT_NAME}}", "")
    html = html.replace("{{RECIPIENT_FIRST_NAME}}", "")
    html = html.replace("{{RECIPIENT_EMAIL}}", "")
    html = html.replace("{{GREETING}}", "LET&#x27;S CONNECT")
    html = html.replace("{{CONTEXT_QUOTE}}", "Pick a time that works for you. I look forward to our conversation.")
    html = html.replace("{{CLOSING}}", "")
    html = html.replace("{{CAL_LINK}}", _escape_html(cal_link))
    html = html.replace("{{DURATION}}", "30")
    html = html.replace("{{MEETING_TYPE}}", "none")
    html = html.replace("{{MEETING_LABEL}}", "")
    html = html.replace("{{EVENT_TYPE_ID}}", str(mt_config["event_type_id"]))
    html = html.replace("{{EVENT_SLUG}}", _escape_html(mt_config["slug"]))
    # JS-safe values for <script> context
    html = html.replace("{{JS_SLUG}}", "")
    html = html.replace("{{JS_BASE_URL}}", _escape_js(base_url))
    html = html.replace("{{JS_RECIPIENT_FIRST_NAME}}", "")
    html = html.replace("{{JS_EVENT_SLUG}}", _escape_js(mt_config["slug"]))
    html = html.replace("{{JS_MEETING_LABEL}}", "")

    if _is_crawler(request):
        prefetched = "null"
    else:
        prefetched = await _prefetch_slots_json(mt_config["slug"])
    html = html.replace("{{PRELOADED_SLOTS}}", prefetched)
    html = html.replace("{{OWNER_NAME}}", _escape_html(config.OWNER_NAME))
    html = html.replace("{{OWNER_FIRST_NAME}}", _escape_js(config.OWNER_FIRST_NAME))

    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300"})


@router.get("/book/{slug}", response_class=HTMLResponse)
async def serve_booking_page(slug: str, request: Request):
    """Serve a personalized booking page."""
    def _fetch_invite():
        with _get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM booking_invites WHERE slug = %s", (slug,))
            return cur.fetchone()

    try:
        invite = await asyncio.get_event_loop().run_in_executor(None, _fetch_invite)
    except Exception:
        logger.exception("DB error fetching invite")
        raise HTTPException(status_code=500, detail="Database error")

    no_cache = {"Cache-Control": "private, no-store, max-age=0"}

    if not invite:
        return HTMLResponse(
            content=_error_page(
                "Link not found",
                "This booking link doesn't exist. It may have been removed or the URL is incorrect.",
            ),
            status_code=404,
            headers=no_cache,
        )

    if invite["status"] != "active":
        msg = {
            "booked": "This meeting has already been booked. Thanks for your interest!",
            "expired": "This booking link has expired. Reach out directly if you'd still like to connect.",
            "cancelled": "This booking link is no longer active.",
        }
        return HTMLResponse(
            content=_error_page(
                "Link no longer active",
                msg.get(invite["status"], "This booking link is no longer active."),
            ),
            status_code=410,
            headers=no_cache,
        )

    # Auto-expire check
    if invite.get("expires_at") and invite["expires_at"].timestamp() < time.time():
        def _expire():
            with _get_db() as c, c.cursor() as cu:
                cu.execute("UPDATE booking_invites SET status = 'expired' WHERE id = %s", (invite["id"],))
                c.commit()

        try:
            await asyncio.get_event_loop().run_in_executor(None, _expire)
        except Exception:
            logger.warning("Failed to auto-expire invite %s", slug)
        return HTMLResponse(
            content=_error_page(
                "Link expired",
                "This booking link has expired. Reach out directly if you'd still like to connect.",
            ),
            status_code=410,
            headers=no_cache,
        )

    # Determine meeting type early so we can start prefetch immediately
    meeting_type = invite.get("meeting_type") or config.DEFAULT_MEETING_TYPE
    mt_config = config.MEETING_TYPES.get(meeting_type, config.MEETING_TYPES[config.DEFAULT_MEETING_TYPE])

    # Skip Cal.com prefetch for crawlers (they only need OG tags, not calendar slots)
    is_crawler = _is_crawler(request)
    prefetch_task = None
    if not is_crawler:
        prefetch_task = asyncio.create_task(_prefetch_slots_json(mt_config["slug"]))

    # View count in thread to avoid blocking the event loop
    def _bump_views():
        try:
            with _get_db() as conn_vc, conn_vc.cursor() as cur_vc:
                cur_vc.execute(
                    "UPDATE booking_invites SET view_count = COALESCE(view_count, 0) + 1 WHERE id = %s",
                    (invite["id"],),
                )
                conn_vc.commit()
        except Exception:
            logger.warning("Failed to increment view_count for %s", slug)

    asyncio.get_event_loop().run_in_executor(None, _bump_views)

    # Build the page from template (fast, CPU-only)
    template = _get_template()
    cal_link = invite.get("cal_link") or f"{config.CAL_USERNAME}/{mt_config['slug']}"
    base_url = config.BASE_URL
    first_name = invite["recipient_first_name"]

    # Personal OG text for link previews (WhatsApp, LinkedIn, etc.)
    if meeting_type == "coffee_chat":
        default_og_title = f"{first_name}, let's grab a coffee"
        default_og_desc = "Pick a time and let's catch up. Looking forward to it!"
    else:
        default_og_title = f"{first_name}, let's connect"
        default_og_desc = "Pick a time that works for you. Looking forward to our conversation."
    og_title = invite.get("og_title") or default_og_title
    og_desc = invite.get("og_description") or default_og_desc

    # Theme: coffee_chat gets warm cafe theme, everything else gets duckweed
    theme = "coffee" if meeting_type == "coffee_chat" else "duckweed"
    bg_image_map = {
        "coffee": f"{base_url}/book/static/cafe-scene.webp",
        "duckweed": f"{base_url}/book/static/duckweed-farm.webp",
    }

    html = template
    html = html.replace("{{SLUG}}", slug)
    html = html.replace("{{BASE_URL}}", base_url)
    html = html.replace("{{THEME}}", theme)
    html = html.replace("{{BG_IMAGE}}", bg_image_map.get(theme, bg_image_map["duckweed"]))
    html = html.replace("{{OG_TITLE}}", _escape_html(og_title))
    html = html.replace("{{OG_DESCRIPTION}}", _escape_html(og_desc))
    html = html.replace("{{OG_IMAGE_URL}}", f"{base_url}/book/og/{slug}.jpg")
    html = html.replace("{{RECIPIENT_NAME}}", _escape_html(invite["recipient_name"]))
    html = html.replace("{{RECIPIENT_FIRST_NAME}}", _escape_html(first_name))
    html = html.replace("{{RECIPIENT_EMAIL}}", _escape_html(invite.get("recipient_email") or ""))
    html = html.replace("{{GREETING}}", _escape_html(invite.get("greeting") or "A note for"))
    html = html.replace("{{CONTEXT_QUOTE}}", _escape_html(invite.get("context_quote") or ""))
    html = html.replace("{{CLOSING}}", _escape_html(invite.get("closing") or "Looking forward to the conversation."))
    html = html.replace("{{CAL_LINK}}", _escape_html(cal_link))
    html = html.replace("{{DURATION}}", str(invite.get("duration_minutes") or 20))
    html = html.replace("{{MEETING_TYPE}}", _escape_html(meeting_type))
    html = html.replace("{{MEETING_LABEL}}", _escape_html(mt_config["label"]))
    html = html.replace("{{EVENT_TYPE_ID}}", str(mt_config["event_type_id"]))
    html = html.replace("{{EVENT_SLUG}}", _escape_html(mt_config["slug"]))
    # JS-safe values for <script> context
    html = html.replace("{{JS_SLUG}}", _escape_js(slug))
    html = html.replace("{{JS_BASE_URL}}", _escape_js(base_url))
    html = html.replace("{{JS_RECIPIENT_FIRST_NAME}}", _escape_js(first_name))
    html = html.replace("{{JS_EVENT_SLUG}}", _escape_js(mt_config["slug"]))
    html = html.replace("{{JS_MEETING_LABEL}}", _escape_js(mt_config["label"]))

    # Await the Cal.com prefetch (started earlier, runs in parallel with view count + template)
    if prefetch_task:
        prefetched = await prefetch_task
    else:
        prefetched = "null"
    html = html.replace("{{PRELOADED_SLOTS}}", prefetched)
    html = html.replace("{{OWNER_NAME}}", _escape_html(config.OWNER_NAME))
    html = html.replace("{{OWNER_FIRST_NAME}}", _escape_js(config.OWNER_FIRST_NAME))

    return HTMLResponse(content=html, headers=no_cache)


# ── Admin endpoints ──────────────────────────────────────────────


@router.post("/api/v1/invites")
async def create_invite(invite: InviteCreate, request: Request):
    """Create a personalized booking invite."""
    _require_api_key(request)

    slug = _slugify(invite.recipient_name)
    meeting_type = invite.meeting_type or config.DEFAULT_MEETING_TYPE
    mt_config = config.MEETING_TYPES.get(meeting_type, config.MEETING_TYPES[config.DEFAULT_MEETING_TYPE])
    cal_link = invite.cal_link or f"{config.CAL_USERNAME}/{mt_config['slug']}"
    duration = invite.duration_minutes or mt_config.get("duration", 20)

    expires_days = invite.expires_days or 30

    try:
        with _get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO booking_invites (
                    slug, contact_id, recipient_name, recipient_first_name,
                    recipient_email, greeting, context_quote, closing,
                    cal_link, duration_minutes, og_title, og_description,
                    meeting_type, status, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active',
                          NOW() + make_interval(days => %s))
                RETURNING id, slug, recipient_name, status, meeting_type, expires_at
            """, (
                slug,
                invite.contact_id,
                invite.recipient_name,
                invite.recipient_first_name,
                invite.recipient_email,
                invite.greeting,
                invite.context_quote,
                invite.closing,
                cal_link,
                duration,
                invite.og_title,
                invite.og_description,
                meeting_type,
                expires_days,
            ))
            created = cur.fetchone()
            conn.commit()
    except Exception:
        logger.exception("DB error creating invite")
        raise HTTPException(status_code=500, detail="Failed to create invite")

    url = f"{config.BASE_URL}/book/{slug}"

    return JSONResponse(content={
        "id": str(created["id"]),
        "slug": slug,
        "url": url,
        "recipient_name": invite.recipient_name,
        "meeting_type": meeting_type,
        "meeting_label": mt_config["label"],
        "status": "active",
        "expires_at": created["expires_at"].isoformat() if created.get("expires_at") else None,
    })


@router.get("/api/v1/invites")
async def list_invites(request: Request, status: Optional[str] = None):
    """List all booking invites."""
    _require_api_key(request)

    try:
        with _get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if status:
                cur.execute("""
                    SELECT id, slug, recipient_name, recipient_email, status,
                           cal_link, meeting_type, duration_minutes,
                           view_count, created_at, booked_at
                    FROM booking_invites WHERE status = %s
                    ORDER BY created_at DESC
                """, (status,))
            else:
                cur.execute("""
                    SELECT id, slug, recipient_name, recipient_email, status,
                           cal_link, meeting_type, duration_minutes,
                           view_count, created_at, booked_at
                    FROM booking_invites ORDER BY created_at DESC
                """)
            rows = cur.fetchall()
    except Exception:
        logger.exception("DB error listing invites")
        raise HTTPException(status_code=500, detail="Database error")

    base_url = config.BASE_URL
    invites = []
    generic_views = 0
    for row in rows:
        # Separate the _generic sentinel row
        if row["slug"] == "_generic":
            generic_views = row.get("view_count") or 0
            continue
        mt = row.get("meeting_type") or config.DEFAULT_MEETING_TYPE
        mt_cfg = config.MEETING_TYPES.get(mt, config.MEETING_TYPES[config.DEFAULT_MEETING_TYPE])
        invites.append({
            "id": str(row["id"]),
            "slug": row["slug"],
            "recipient_name": row["recipient_name"],
            "recipient_email": row.get("recipient_email"),
            "status": row["status"],
            "meeting_type": mt,
            "meeting_label": mt_cfg["label"] or mt.replace("_", " ").title(),
            "duration_minutes": row.get("duration_minutes") or mt_cfg["duration"],
            "view_count": row.get("view_count") or 0,
            "url": f"{base_url}/book/{row['slug']}",
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "booked_at": row["booked_at"].isoformat() if row.get("booked_at") else None,
        })

    return JSONResponse(content={"invites": invites, "count": len(invites), "generic_views": generic_views})


@router.patch("/api/v1/invites/{invite_id}")
async def update_invite(invite_id: str, update: InviteUpdate, request: Request):
    """Update an invite (e.g., change status, context)."""
    _require_api_key(request)

    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Resolve meeting_type into DB columns
    if "meeting_type" in updates:
        mt = updates.pop("meeting_type")
        mt_config = config.MEETING_TYPES.get(mt)
        if not mt_config:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid meeting_type '{mt}'. Must be one of: {', '.join(sorted(config.MEETING_TYPES.keys()))}",
            )
        updates["meeting_type"] = mt
        updates["cal_link"] = f"{config.CAL_USERNAME}/{mt_config['slug']}"
        updates["meeting_label"] = mt_config["label"]
        updates["duration_minutes"] = mt_config["duration"]

    if "status" in updates and updates["status"] not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{updates['status']}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    set_clauses = ", ".join(f"{k} = %s" for k in updates.keys())
    values = list(updates.values()) + [invite_id]

    try:
        with _get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE booking_invites SET {set_clauses} WHERE id = %s RETURNING *",
                values,
            )
            result = cur.fetchone()
            conn.commit()
    except Exception:
        logger.exception("DB error updating invite")
        raise HTTPException(status_code=500, detail="Database error")

    if not result:
        raise HTTPException(status_code=404, detail="Invite not found")

    return JSONResponse(content={"status": "updated", "id": str(result["id"])})


@router.delete("/api/v1/invites/{invite_id}")
async def delete_invite(invite_id: str, request: Request):
    """Permanently delete a booking invite."""
    _require_api_key(request)

    try:
        with _get_db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM booking_invites WHERE id = %s RETURNING id", (invite_id,))
            deleted = cur.fetchone()
            conn.commit()
    except Exception:
        logger.exception("DB error deleting invite")
        raise HTTPException(status_code=500, detail="Database error")

    if not deleted:
        raise HTTPException(status_code=404, detail="Invite not found")

    return JSONResponse(content={"status": "deleted", "id": invite_id})


@router.post("/api/v1/admin/fix-cal-titles")
async def fix_cal_titles(request: Request):
    """Update Cal.com event type title templates to 'Person & Owner | Type'.

    Uses Cal.com template variable {Scheduler} for the attendee name.
    Run once after deploy to fix calendar event titles for all future bookings.
    """
    _require_api_key(request)

    results = []
    for mt_key, mt_cfg in config.MEETING_TYPES.items():
        if mt_key == "none":
            continue
        template = "{Scheduler} & " + config.OWNER_FIRST_NAME + " | " + mt_cfg["label"]
        try:
            await update_event_type_title(mt_cfg["event_type_id"], template)
            results.append({"type": mt_key, "label": mt_cfg["label"], "template": template, "status": "updated"})
        except Exception as e:
            logger.exception("Failed to update Cal.com title for %s", mt_key)
            results.append({"type": mt_key, "label": mt_cfg["label"], "template": template, "status": "failed", "error": str(e)})

    return JSONResponse(content={"results": results})


@router.get("/api/v1/admin/cal-event-types")
async def get_cal_event_types(request: Request):
    """Fetch current Cal.com event type settings (for debugging title templates)."""
    _require_api_key(request)

    results = []
    for mt_key, mt_cfg in config.MEETING_TYPES.items():
        if mt_key == "none":
            continue
        try:
            data = await get_event_type(mt_cfg["event_type_id"])
            results.append({"type": mt_key, "event_type_id": mt_cfg["event_type_id"], "data": data})
        except Exception as e:
            results.append({"type": mt_key, "event_type_id": mt_cfg["event_type_id"], "error": str(e)})

    return JSONResponse(content={"results": results})


# ── Cal.com proxy endpoints ──────────────────────────────────────


class BookingRequest(BaseModel):
    start: str  # ISO 8601 UTC
    name: str
    email: str
    timezone: str = "Asia/Singapore"
    notes: Optional[str] = None
    guests: Optional[list[str]] = None
    invite_slug: Optional[str] = None  # to track which invite triggered the booking
    event_type_id: Optional[int] = None  # Cal.com event type ID for meeting type

    @field_validator("guests")
    @classmethod
    def validate_guests(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) > 5:
            raise ValueError("Maximum 5 guest emails allowed")
        email_re = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
        for g in v:
            if not email_re.match(g):
                raise ValueError(f"Invalid guest email: {g}")
        return v


@router.get("/api/v1/cal/slots")
async def get_cal_slots(
    start: str,
    end: str,
    tz: str = "Asia/Singapore",
    event_slug: Optional[str] = None,
):
    """Proxy to Cal.com slots API. Returns available time slots."""
    try:
        slots = await get_available_slots(
            start=start, end=end, timezone=tz, event_slug=event_slug,
        )
        return JSONResponse(content={"slots": slots})
    except Exception:
        logger.exception("Failed to fetch Cal.com slots")
        raise HTTPException(status_code=502, detail="Failed to fetch availability")


@router.post("/api/v1/cal/book")
async def create_cal_booking(booking: BookingRequest, request: Request):
    """Create a booking via Cal.com API. Public endpoint (invitees use this)."""
    client_ip = request.client.host if request.client else "unknown"
    # Keyed separately from admin login: "book:{ip}" vs raw ip
    if not _check_rate_limit(f"book:{client_ip}", window=3600, max_attempts=10):
        raise HTTPException(status_code=429, detail="Too many booking attempts. Please try again later.")
    try:
        meta = {"source": "jarvis-booking-service"}
        if booking.invite_slug:
            meta["invite_slug"] = booking.invite_slug

        # Calendar event titles are controlled via eventName templates on the
        # Cal.com event type (configured via /api/v1/admin/fix-cal-titles).
        result = await create_booking(
            start=booking.start,
            attendee_name=booking.name,
            attendee_email=booking.email,
            attendee_timezone=booking.timezone,
            notes=booking.notes,
            guests=booking.guests,
            metadata=meta,
            event_type_id=booking.event_type_id,
        )

        # If we have an invite slug, mark it as booked (unless reusable)
        if booking.invite_slug:
            try:
                with _get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT reusable FROM booking_invites WHERE slug = %s",
                        (booking.invite_slug,),
                    )
                    inv = cur.fetchone()
                    if inv and not inv["reusable"]:
                        cur.execute(
                            "UPDATE booking_invites SET status = 'booked', booked_at = NOW() WHERE slug = %s",
                            (booking.invite_slug,),
                        )
                    conn.commit()
            except Exception:
                logger.warning("Failed to update invite status for %s", booking.invite_slug)

        return JSONResponse(content={"status": "booked", "data": result.get("data", {})})
    except httpx.HTTPStatusError as e:
        logger.exception("Cal.com booking HTTP error %s", e.response.status_code)
        if e.response.status_code == 400:
            cal_msg = ""
            try:
                cal_err = e.response.json()
                cal_msg = cal_err.get("error", {}).get("message", "")
            except Exception:
                pass
            cal_lower = cal_msg.lower()
            # Slot/availability errors
            if "slot" in cal_lower or "unavailable" in cal_lower or "busy" in cal_lower:
                detail = "This time slot is no longer available. Please go back and pick another time."
            # Character limit errors (notes or other fields)
            elif "max_characters_allowed" in cal_lower or "max_characters" in cal_lower:
                logger.error("Cal.com field character limit exceeded: %s", cal_msg)
                detail = "Your notes are too long. Please shorten them and try again."
            # Email validation errors
            elif "email" in cal_lower and ("invalid" in cal_lower or "valid" in cal_lower):
                detail = "Please check the email address and try again."
            else:
                logger.error("Cal.com rejected booking payload: %s", cal_msg)
                detail = "Booking failed. Please try again or pick a different time."
            raise HTTPException(status_code=400, detail=detail)
        if e.response.status_code >= 500:
            raise HTTPException(status_code=502, detail="Cal.com is temporarily unavailable. Please try again in a moment.")
        raise HTTPException(status_code=502, detail="Failed to create booking. Please try again.")
    except httpx.TimeoutException:
        logger.exception("Cal.com booking request timed out")
        raise HTTPException(status_code=504, detail="Booking request timed out. Please try again in a moment.")
    except Exception:
        logger.exception("Failed to create Cal.com booking")
        raise HTTPException(status_code=502, detail="Failed to create booking. Please try again.")


# ── Helpers ──────────────────────────────────────────────────────


def _escape_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _escape_js(text: str) -> str:
    """Escape text for safe embedding inside JS single-quoted strings."""
    return (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("/", "\\/")  # prevents </script> breaking out
    )


async def _prefetch_slots_json(event_slug: str) -> str:
    """Pre-fetch ~4 months of Cal.com slots server-side for embedding in HTML.

    Eliminates 3 client-side round trips through Firebase (~1.7s each).
    Returns a JSON string safe for <script> embedding, or "null" on failure.
    """
    today = date.today()
    start = today.replace(day=1)
    # Cover current month + 3 more
    target_month = today.month + 4
    target_year = today.year
    while target_month > 12:
        target_month -= 12
        target_year += 1
    end = date(target_year, target_month, 1) - timedelta(days=1)

    try:
        slots = await get_available_slots(
            start=start.isoformat(),
            end=end.isoformat(),
            event_slug=event_slug,
        )
        payload = json.dumps({"slots": slots, "tz": "Asia/Singapore"})
        return payload.replace("</", "<\\/")  # prevent </script> breakout
    except Exception:
        logger.warning("Failed to prefetch slots for %s", event_slug)
        return "null"
