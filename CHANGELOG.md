# Changelog

## 2026-03-23 — Initial Release

- Personalized booking pages with custom greetings and context messages
- Dynamic OG image generation (Pillow) for WhatsApp/LinkedIn/Telegram previews
- Cal.com API v2 integration (availability slots + booking creation)
- Admin dashboard for managing invites
- Multiple meeting types: Quick Call, Discovery Call, Coffee Chat, Extended Call, Deep Dive
- Themed backgrounds (duckweed farm, cafe scene)
- International character transliteration in URL slugs
- Server-side slot prefetching (eliminates client round trips)
- Crawler detection for fast social bot responses
- In-memory rate limiting (admin login + booking creation)
- Docker deployment with health check
- Configurable owner identity via environment variables
