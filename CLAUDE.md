# Booking Service — Personalized Booking Links

## Overview
FastAPI service that generates personalized calendar booking URLs for outreach. Each contact gets a custom booking page (e.g., `book.example.com/book/jonas-0e2e`) with their name, context message, themed backgrounds, and dynamic OG images for WhatsApp/LinkedIn previews.

## Architecture
- **Backend:** Python 3.11 + FastAPI + uvicorn
- **Database:** PostgreSQL via Supabase (`booking_invites` table)
- **Calendar:** Cal.com API v2 (slots + bookings)
- **OG Images:** Pillow (dynamic JPEG generation)
- **Frontend:** Vanilla HTML/CSS/JS (server-side template replacement)
- **Deployment:** Docker on Hetzner VPS, Caddy reverse proxy

## Key Files
- `app/config.py` — Central config (Cal.com IDs, owner name, meeting types)
- `app/routes.py` — All API endpoints + page rendering (~890 lines)
- `app/cal_client.py` — Cal.com API v2 client with retries
- `app/og_image.py` — Pillow-based OG image generation
- `templates/booking.html` — Main booking page template
- `templates/admin.html` — Admin dashboard
- `static/` — Avatar, background images

## Cal.com Event Types
| Type | ID | Slug | Duration |
|------|-----|------|----------|
| Discovery Call | 5120977 | discovery-call | 20m |
| Coffee Chat | 5120981 | coffee-chat | 30m |
| Deep Dive | 5120983 | deep-dive | 60m |

Cal.com username: `your-username`

## Deployment
- **Domain:** `book.example.com`
- **VPS:** Hetzner 0.0.0.0 (claw user)
- **Reverse proxy:** Caddy (auto-HTTPS)
- **Container:** `docker compose up --build -d`
- **Health check:** `GET /health`

## Admin
- Dashboard: `https://book.example.com/book/admin`
- API: `POST /api/v1/invites` with `X-API-Key` header
- Auth: `POST /api/v1/admin/auth` with password

## Progress
See [PROGRESS.md](PROGRESS.md) for session log.
