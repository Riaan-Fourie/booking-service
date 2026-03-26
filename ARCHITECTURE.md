# Architecture

## Overview

FastAPI service that generates personalized calendar booking URLs for outreach. Each contact gets a custom booking page (e.g., `book.example.com/book/jonas-0e2e`) with their name, a context message, themed backgrounds, and dynamic OG images for WhatsApp/LinkedIn previews.

## Stack

- **Backend:** Python 3.11 + FastAPI + uvicorn
- **Database:** PostgreSQL (via Supabase or any PostgreSQL instance)
- **Calendar:** Cal.com API v2 (availability slots + booking creation)
- **OG Images:** Pillow (dynamic JPEG generation)
- **Frontend:** Vanilla HTML/CSS/JS (server-side template replacement)
- **Deployment:** Docker, reverse proxy (Caddy/Nginx) recommended

## Project Structure

```
main.py                 # FastAPI app entrypoint, CORS, health check
app/
  config.py             # Central config (env vars, Cal.com IDs, meeting types)
  routes.py             # All API endpoints + page rendering
  cal_client.py         # Cal.com API v2 client with retry logic
  og_image.py           # Pillow-based dynamic OG image generation
templates/
  booking.html          # Main booking page template
  admin.html            # Admin dashboard
static/                 # Avatar, background images
tests/                  # pytest test suite
```

## Key Design Decisions

### Server-Side Template Replacement

The booking page is a single HTML template with `{{PLACEHOLDER}}` tokens. The server replaces these with per-invite values before serving. This avoids client-side rendering and ensures OG meta tags are present when crawlers hit the page.

### Crawler Detection

Social media bots (WhatsApp, Telegram, LinkedIn, etc.) are detected via user-agent string matching. Crawlers receive the page with OG tags but skip the Cal.com slot prefetch, since they only need metadata for link previews.

### OG Image Pipeline

Dynamic Open Graph images are generated per-invite using Pillow:

1. Background images are pre-composited with gradient overlays at module load
2. Per-invite images add personalized text (recipient name + owner name)
3. Images are sharpened with UnsharpMask to survive WhatsApp JPEG re-compression
4. Results are LRU-cached (128 entries) to avoid regeneration
5. Output: 1200x630 JPEG, ~40-60KB

### Slug Generation

Invite URLs use human-readable slugs derived from the recipient's name:
- International characters are transliterated (e.g., `u` for `u`, `ss` for `ss`)
- Non-alphanumeric characters become hyphens
- Collision detection appends a 4-character hex suffix only when needed

### Cal.com Integration

- **Slots API** (`GET /api/v1/cal/slots`): Proxies Cal.com availability. The server prefetches ~4 months of slots and embeds them in the HTML to eliminate client-side round trips.
- **Booking API** (`POST /api/v1/cal/book`): Creates bookings via Cal.com v2 API. Handles slot conflicts, field validation errors, and timeout retries.
- **Event Types**: Multiple meeting types (discovery call, coffee chat, deep dive) map to Cal.com event type IDs configured in `app/config.py`.

### Rate Limiting

In-memory per-IP rate limiting protects:
- Admin login: 5 attempts per 5-minute window
- Booking creation: 10 attempts per hour

### Security

- API key authentication for admin endpoints (`X-API-Key` header)
- Constant-time password comparison (`hmac.compare_digest`)
- HTML escaping for all template values (XSS prevention)
- JS escaping for values embedded in `<script>` contexts
- `robots.txt` blocks indexing of booking and API paths
- Path traversal prevention on static file serving

## API Endpoints

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/book` | Generic booking page (no personalization) |
| `GET` | `/book/{slug}` | Personalized booking page |
| `GET` | `/book/og/{slug}.jpg` | Dynamic OG image |
| `GET` | `/book/static/{file}` | Static assets |
| `GET` | `/api/v1/cal/slots` | Cal.com availability proxy |
| `POST` | `/api/v1/cal/book` | Create a booking |

### Admin (requires `X-API-Key` header)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/auth` | Exchange password for API key |
| `POST` | `/api/v1/invites` | Create a new invite |
| `GET` | `/api/v1/invites` | List all invites |
| `PATCH` | `/api/v1/invites/{id}` | Update an invite |
| `DELETE` | `/api/v1/invites/{id}` | Delete an invite |
| `POST` | `/api/v1/admin/fix-cal-titles` | Update Cal.com event title templates |
| `GET` | `/api/v1/admin/cal-event-types` | Debug Cal.com event type config |
| `GET` | `/book/admin` | Admin dashboard UI |

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | (required) |
| `BOOKING_API_KEY` | API key for admin endpoints | (required) |
| `ADMIN_PASSWORD` | Password for admin login | (required) |
| `CAL_API_KEY` | Cal.com API key | (required) |
| `CAL_USERNAME` | Cal.com username | `your-username` |
| `BASE_URL` | Public base URL | `https://book.example.com` |
| `OWNER_NAME` | Full name for templates/OG images | `Your Name` |
| `OWNER_FIRST_NAME` | First name for personalized text | `Owner` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `*` |
| `PORT` | Server port | `8080` |

## Docker Deployment

```bash
cp .env.example .env
# Edit .env with your values
docker compose up --build -d
```

The service listens on the configured `PORT` (default 8080). Place a reverse proxy (Caddy, Nginx, Traefik) in front for HTTPS termination.

## Database Schema

The service uses a single `booking_invites` table:

```sql
CREATE TABLE booking_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    contact_id TEXT,
    recipient_name TEXT NOT NULL,
    recipient_first_name TEXT NOT NULL,
    recipient_email TEXT,
    greeting TEXT DEFAULT 'A note for',
    context_quote TEXT,
    closing TEXT DEFAULT 'Looking forward to the conversation.',
    cal_link TEXT,
    duration_minutes INTEGER DEFAULT 20,
    og_title TEXT,
    og_description TEXT,
    meeting_type TEXT DEFAULT 'coffee_chat',
    meeting_label TEXT,
    status TEXT DEFAULT 'active',
    reusable BOOLEAN DEFAULT FALSE,
    view_count INTEGER DEFAULT 0,
    expires_at TIMESTAMPTZ,
    booked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
