# Booking Service

Personalized booking link service with Cal.com integration. Each contact gets a unique URL with their name, a context message, and themed booking page.

## Features
- Personalized booking pages with custom greetings
- Dynamic OG images for WhatsApp/LinkedIn/Telegram previews
- Cal.com integration (availability slots + booking creation)
- Admin dashboard for managing invites
- Crawler detection for fast social media bot responses
- Rate limiting and security hardening

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your values

# Run locally
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## Docker Deployment

```bash
docker compose up --build -d
```

## Meeting Types
| Type | Duration | Theme |
|------|----------|-------|
| Discovery Call | 20 min | Green (duckweed) |
| Coffee Chat | 30 min | Amber (cafe) |
| Deep Dive | 60 min | Green (duckweed) |

## Admin
- Dashboard: `/book/admin`
- Create invite: `POST /api/v1/invites`
- List invites: `GET /api/v1/invites`

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for full setup instructions.
