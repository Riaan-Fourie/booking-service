# Booking Service — Personalized Booking Links

## Overview
FastAPI service that generates personalized calendar booking URLs for outreach. Each contact gets a custom booking page (e.g., `book.example.com/book/jonas-0e2e`) with their name, context message, themed backgrounds, and dynamic OG images for WhatsApp/LinkedIn previews.

## Architecture
- **Backend:** Python 3.11 + FastAPI + uvicorn
- **Database:** PostgreSQL via Supabase (`booking_invites` table)
- **Calendar:** Cal.com API v2 (slots + bookings)
- **OG Images:** Pillow (dynamic JPEG generation)
- **Frontend:** Vanilla HTML/CSS/JS (server-side template replacement)
- **Deployment:** Docker on any VPS, reverse proxy (Caddy/Nginx) recommended

## Key Files
- `app/config.py` — Central config (Cal.com IDs, owner name, meeting types)
- `app/routes.py` — All API endpoints + page rendering
- `app/cal_client.py` — Cal.com API v2 client with retries
- `app/og_image.py` — Pillow-based OG image generation
- `templates/booking.html` — Main booking page template
- `templates/admin.html` — Admin dashboard
- `static/` — Avatar, background images

## Cal.com Event Types
Configure your Cal.com event type IDs in `app/config.py` under `MEETING_TYPES`. Each entry needs:
- `event_type_id` — from your Cal.com dashboard URL when editing the event type
- `slug` — the URL slug for the event type
- `label` — display name
- `duration` — meeting length in minutes

## Deployment
- **Domain:** Configure via `BASE_URL` env var
- **Reverse proxy:** Caddy or Nginx (auto-HTTPS recommended)
- **Container:** `docker compose up --build -d`
- **Health check:** `GET /health`

## Admin
- Dashboard: `https://<your-domain>/book/admin`
- API: `POST /api/v1/invites` with `X-API-Key` header
- Auth: `POST /api/v1/admin/auth` with password

## Progress
See [PROGRESS.md](PROGRESS.md) for session log.
