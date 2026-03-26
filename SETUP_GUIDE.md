# Personalized Booking Service - Setup Guide

> **Give this entire folder to Claude Code** and ask it to help you set up your own personalized booking service. This guide contains all the code and context needed.

## What This Is

A **personalized booking link service** that creates unique calendar booking URLs for outreach and networking. Each contact gets a custom booking page (e.g., `yourdomain.com/book/jonas-0e2e`) with:

- A personalized left panel with the recipient's name, a context quote, and your avatar
- A native calendar UI (no iframe) that fetches availability from Cal.com
- Dynamic OG images for beautiful link previews on WhatsApp, LinkedIn, Telegram, etc.
- Themed backgrounds (e.g., warm coffee theme for casual chats, professional theme for discovery calls)
- An admin dashboard to create/manage invites
- Auto-expiring links, view tracking, and booking status management

## Architecture Overview

```
yourdomain.com/book/{slug}
         |
    Reverse Proxy / Hosting (Firebase, Cloudflare, Nginx, etc.)
         |
    Cloud Run / Docker / VPS: FastAPI (Python 3.11)
         |
    +----------+
    |  HTML    |-- OG tags (personalized title/desc/image for link previews)
    | Template |-- Left panel: name, context quote, avatar photo
    |          |-- Right panel: native calendar (fetches Cal.com slots via backend)
    +----------+
         |
    Cal.com API v2: availability slots, booking creation, calendar invites
    PostgreSQL (Supabase or self-hosted): booking_invites table
```

## Tech Stack

- **Backend**: Python 3.11, FastAPI, psycopg2, Pillow (OG images), httpx, tenacity
- **Frontend**: Vanilla HTML/CSS/JS (no framework needed), Google Fonts (Inter)
- **Calendar**: Cal.com (free tier works) via API v2
- **Database**: PostgreSQL (Supabase free tier works perfectly)
- **Hosting**: Google Cloud Run (or any Docker host)
- **Optional**: Firebase Hosting for URL routing, Cloudflare for DNS

## What You Need to Customize

### 1. Personal Information (MUST CHANGE)
- **Your name** everywhere (replace "[Example Name]" with your name)
- **Your avatar photo** (replace `static/avatar.webp` with your headshot)
- **Your Cal.com username** (replace `example-user` in config.py)
- **Your domain** (replace `example.com` with your domain)
- **Your meeting types** and Cal.com event type IDs (see Cal.com setup below)

### 2. Visual Theme (SHOULD CUSTOMIZE)
- **Background images** (replace `duckweed-farm.webp/png` and `cafe-scene.webp/png` with your own)
  - You need both `.webp` (for page background, keep under 300KB) and `.png` (for OG image generation via Pillow, can be larger)
- **Color scheme** in `templates/booking.html` - CSS custom properties make this easy:
  - Default theme: `--accent-*` variables (currently green)
  - Coffee theme: `[data-theme="coffee"]` block (currently warm amber/brown)
- **Meeting type labels** (e.g., "Coffee Chat", "Discovery Call", "Deep Dive")
- **Greeting text**, closing lines, badge text

### 3. Infrastructure (MUST SET UP)
- **Cal.com account** with event types configured
- **Supabase project** (or any PostgreSQL database)
- **Hosting** (Cloud Run, Railway, Fly.io, Render, or any Docker host)
- **Domain** with DNS pointing to your host

## Step-by-Step Setup

### Step 1: Cal.com Setup

1. Create a free account at [cal.com](https://cal.com)
2. Create event types for your meeting categories. Example:
   - "Discovery Call" (20 min)
   - "Coffee Chat" (30 min)
   - "Deep Dive" (60 min)
3. Note down each event type's **ID** (visible in the Cal.com URL when editing) and **slug**
4. Generate an API key: Settings > Developer > API Keys
5. Update `app/config.py` with your Cal.com username, event type IDs, slugs, and durations

### Step 2: Database Setup

1. Create a free Supabase project at [supabase.com](https://supabase.com)
2. Run this SQL in the Supabase SQL editor to create the table:

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
    meeting_type TEXT DEFAULT 'discovery_call',
    meeting_label TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'booked', 'expired', 'cancelled')),
    reusable BOOLEAN DEFAULT FALSE,
    view_count INTEGER DEFAULT 0,
    expires_at TIMESTAMPTZ,
    booked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_booking_invites_slug ON booking_invites(slug);
CREATE INDEX idx_booking_invites_status ON booking_invites(status);

-- Optional: insert a sentinel row for tracking generic page views
INSERT INTO booking_invites (slug, recipient_name, recipient_first_name, status, reusable)
VALUES ('_generic', 'Generic', 'Generic', 'active', true);
```

3. Get your database connection string from Supabase: Settings > Database > Connection string (URI)

### Step 3: Environment Variables

Copy `.env.example` to `.env` and fill in:

```
DATABASE_URL=postgresql://postgres:[password]@[host]:6543/postgres
BOOKING_API_KEY=<generate-a-random-api-key>
ADMIN_PASSWORD=<pick-a-memorable-password>
CAL_API_KEY=<your-cal-com-api-key>
CAL_LINK=yourusername/discovery-call
BASE_URL=https://yourdomain.com
PORT=8080
```

Generate a random API key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### Step 4: Customize the Code

Key files to edit:

| File | What to change |
|------|---------------|
| `app/config.py` | Cal.com username, event type IDs/slugs/durations, default meeting type |
| `templates/booking.html` | Your name, avatar path, colors (CSS custom properties), meeting type labels |
| `templates/admin.html` | Your name in the title, domain references |
| `app/og_image.py` | Your name in the OG image text overlay |
| `static/` | Replace avatar and background images with your own |

### Step 5: Run Locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Visit `http://localhost:8080/book` for the generic page, or `http://localhost:8080/book/admin` for the admin dashboard.

### Step 6: Deploy

**Option A: Google Cloud Run (recommended)**
```bash
# Install gcloud CLI, authenticate, then:
gcloud builds submit --config=cloudbuild.yaml --substitutions=COMMIT_SHA=v1 .
```
You'll need to set up secrets in GCP Secret Manager and update `cloudbuild.yaml` with your project ID and secret names.

**Option B: Any Docker host**
```bash
docker build -t booking-service .
docker run -p 8080:8080 --env-file .env booking-service
```

**Option C: Railway / Render / Fly.io**
These platforms auto-detect the Dockerfile. Just connect your repo and set environment variables in their dashboard.

### Step 7: Domain Setup

Point your domain to your hosting. If using Firebase Hosting as a reverse proxy, add a rewrite rule in `firebase.json`:
```json
{
  "rewrites": [
    { "source": "/book/**", "run": { "serviceId": "your-booking-service", "region": "your-region" } },
    { "source": "/api/**", "run": { "serviceId": "your-booking-service", "region": "your-region" } }
  ]
}
```

## How It Works

### Creating an Invite (Programmatic)
```python
import httpx
r = httpx.post(
    "https://yourdomain.com/api/v1/invites",
    json={
        "recipient_name": "Jonas Schmidt",
        "recipient_first_name": "Jonas",
        "context_quote": "Saw your talk on sustainable agriculture. Would love to discuss collaboration opportunities.",
        "meeting_type": "coffee_chat",
    },
    headers={"X-API-Key": "YOUR_API_KEY"},
)
print(r.json()["url"])  # https://yourdomain.com/book/jonas-schmidt
```

### Creating an Invite (Admin Dashboard)
Visit `https://yourdomain.com/book/admin`, log in with your admin password, and use the "Create New" tab.

### What Happens When Someone Visits a Link
1. Server looks up the invite by slug
2. Checks status (active/booked/expired/cancelled) and shows appropriate page
3. Increments view count
4. Pre-fetches 4 months of Cal.com availability server-side (saves ~2s of client round-trips)
5. Renders personalized HTML with their name, your context quote, and themed background
6. User picks a date, time slot, enters their email, and confirms
7. Backend creates the booking via Cal.com API
8. Invite status is set to "booked"
9. Both parties receive calendar invites via Cal.com

### OG Image Generation
When the link is shared on WhatsApp/LinkedIn/Telegram, crawlers hit `/book/og/{slug}.jpg` which:
1. Uses a pre-computed gradient-overlaid background image (cached at startup)
2. Overlays personalized text ("[Example Names]") using Pillow
3. Returns a JPEG (~88KB, optimized for WhatsApp's timeout constraints)

### Theme System
Two themes controlled by CSS custom properties via `data-theme` attribute on `<html>`:
- **Default (duckweed/green)**: For discovery calls and deep dives
- **Coffee (warm amber)**: For coffee chats

Add your own themes by adding a new `[data-theme="mytheme"]` CSS block with your accent colors.

## File Structure

```
booking-service/
├── main.py              # FastAPI app entry point, CORS, health check
├── Dockerfile           # Python 3.11-slim container
├── cloudbuild.yaml      # Google Cloud Build + Cloud Run deploy config
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .dockerignore        # Docker build exclusions
├── .gcloudignore        # Cloud Build exclusions
│
├── app/
│   ├── __init__.py
│   ├── config.py        # Configuration + Cal.com event type mapping
│   ├── routes.py        # All API endpoints and template rendering
│   ├── cal_client.py    # Cal.com API v2 client (slots + bookings)
│   └── og_image.py      # Pillow-based OG image generation
│
├── templates/
│   ├── booking.html     # Main booking page (responsive, themed, native calendar)
│   └── admin.html       # Admin dashboard (password-protected)
│
└── static/
    ├── avatar-*.webp    # Your headshot (keep small, ~5KB)
    ├── *-farm.png       # OG image source (used by Pillow, can be larger)
    ├── *-farm.webp      # Page background (optimized, <300KB)
    ├── cafe-scene.png   # Coffee theme OG source
    └── cafe-scene.webp  # Coffee theme background
```

## Key Design Decisions

- **No frontend framework**: Vanilla HTML/CSS/JS keeps it fast and simple. The entire booking page is a single HTML file with inline CSS and JS.
- **Server-side slot prefetch**: Cal.com slots are fetched server-side and embedded in the HTML, eliminating 3 client round-trips (~2s savings).
- **Crawler fast-path**: Social media crawlers get minimal HTML with just OG tags (no Cal.com API calls).
- **In-memory rate limiting**: Simple per-IP throttling. For multi-instance deployments, replace with Redis.
- **JPEG OG images**: WhatsApp times out on large PNGs. JPEG at quality 92 with UnsharpMask keeps text crisp at ~88KB.
- **Template placeholders**: `{{VARIABLE}}` strings in HTML are replaced server-side. Simple and fast.

## Tips

- **Image optimization**: Use `cwebp` to convert backgrounds to WebP. Keep page backgrounds under 300KB for fast loading.
- **Custom fonts**: The OG image generator uses DejaVu (Linux) or Segoe UI (Windows). For custom fonts, add `.ttf` files and update `og_image.py`.
- **Multiple themes**: Add new CSS `[data-theme="..."]` blocks for more meeting types.
- **Reusable links**: Set `reusable: true` on an invite to prevent it from being marked as "booked" after one use (useful for email signatures).
- **Generic page**: The `/book` endpoint (no slug) serves a generic booking page. Great for email signatures.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Cal.com slots not loading | Check `CAL_API_KEY` and event type IDs in config. Test with `curl https://api.cal.com/v2/slots?...` |
| OG images not showing | Ensure `.png` source images exist in `static/`. Check Pillow is installed with JPEG support. |
| Database connection fails | Verify `DATABASE_URL` format. Supabase uses port 6543 for connection pooling. |
| Admin login fails | Check `ADMIN_PASSWORD` env var is set. Rate limiter blocks after 5 attempts per 5 minutes. |
| Fonts missing in Docker | The Dockerfile installs `fonts-dejavu-core`. If using custom fonts, add them to the Dockerfile. |
