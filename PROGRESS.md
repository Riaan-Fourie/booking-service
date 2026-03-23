# Progress Log

## 2026-03-23 — Initial Setup & Rebranding

### What was done
- Rebranded from "[Previous Owner]" to "Owner Name" across all files
- Made owner name config-driven (`OWNER_NAME`, `OWNER_FIRST_NAME` env vars)
- Updated Cal.com config with Owner's account:
  - Username: `your-username`
  - Created 3 event types: Discovery Call (5120977), Coffee Chat (5120981), Deep Dive (5120983)
  - Generated API key
- Created docker-compose.yml for Hetzner deployment
- Added curl to Dockerfile for healthcheck
- Removed GCP-specific cloudbuild.yaml
- Updated .env.example with Owner's Supabase + Cal.com config
- Created CLAUDE.md, PROGRESS.md, README.md
- Created `booking_invites` table in Supabase
- Registered in repos.json, added Makefile targets
- Deployed to Hetzner VPS with Caddy reverse proxy

### Files changed
- `app/config.py` — owner name vars, Cal.com IDs, defaults
- `app/og_image.py` — dynamic owner name in OG images
- `app/routes.py` — owner name in error pages, OG titles, Cal titles, template vars
- `app/cal_client.py` — updated docstring
- `templates/booking.html` — rebranded name, avatar, JS badge
- `templates/admin.html` — rebranded name, domain
- `.env.example` — updated for Owner's setup
- `Dockerfile` — added curl
- `docker-compose.yml` — new (Hetzner deployment)
- `static/avatar.webp` — placeholder (copy of original)
