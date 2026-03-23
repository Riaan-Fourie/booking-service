import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Config:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    BOOKING_API_KEY: str = os.getenv("BOOKING_API_KEY", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    CAL_LINK: str = os.getenv("CAL_LINK", "your-username/discovery-call")
    CAL_API_KEY: str = os.getenv("CAL_API_KEY", "")
    CAL_API_BASE: str = "https://api.cal.com/v2"
    CAL_USERNAME: str = os.getenv("CAL_USERNAME", "your-username")
    CAL_EVENT_SLUG: str = "discovery-call"
    CAL_EVENT_TYPE_ID: int = 5120977
    BASE_URL: str = os.getenv("BASE_URL", "https://book.example.com")
    PORT: int = int(os.getenv("PORT", "8080"))

    # Owner identity (used in templates, OG images, error pages)
    OWNER_NAME: str = os.getenv("OWNER_NAME", "Owner Name")
    OWNER_FIRST_NAME: str = os.getenv("OWNER_FIRST_NAME", "Owner")

    # Meeting type → Cal.com event type mapping
    MEETING_TYPES: dict = {
        "discovery_call": {"event_type_id": 5120977, "slug": "discovery-call", "label": "Discovery Call", "duration": 20},
        "coffee_chat": {"event_type_id": 5120981, "slug": "coffee-chat", "label": "Coffee Chat", "duration": 30},
        "deep_dive": {"event_type_id": 5120983, "slug": "deep-dive", "label": "Deep Dive", "duration": 60},
        "none": {"event_type_id": 5120981, "slug": "coffee-chat", "label": "", "duration": 30},
    }
    DEFAULT_MEETING_TYPE: str = "discovery_call"


config = Config()
