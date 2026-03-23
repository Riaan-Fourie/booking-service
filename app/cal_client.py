"""Cal.com API v2 client for fetching availability and creating bookings."""

import logging
from typing import Optional

import httpx
import tenacity

from app.config import config

logger = logging.getLogger("booking.cal_client")

SLOTS_API_VERSION = "2024-09-04"
BOOKINGS_API_VERSION = "2024-08-13"
EVENT_TYPES_API_VERSION = "2024-06-14"

# Cal.com enforces a max character limit on the notes booking field.
# Truncate to stay safely under the limit (default is ~500).
NOTES_MAX_CHARS = 500

def _is_retryable(exc: BaseException) -> bool:
    """Return True if the Cal.com error is transient and worth retrying."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


def _headers(api_version: str) -> dict:
    """Build headers for Cal.com API requests."""
    h = {
        "Content-Type": "application/json",
        "cal-api-version": api_version,
    }
    if config.CAL_API_KEY:
        h["Authorization"] = f"Bearer {config.CAL_API_KEY}"
    return h


async def get_available_slots(
    start: str,
    end: str,
    timezone: str = "Asia/Singapore",
    event_slug: Optional[str] = None,
    username: Optional[str] = None,
) -> dict:
    """Fetch available time slots from Cal.com.

    Args:
        start: Start date in YYYY-MM-DD format.
        end: End date in YYYY-MM-DD format.
        timezone: IANA timezone string.
        event_slug: Cal.com event type slug (default from config).
        username: Cal.com username (default from config).

    Returns:
        Dict with date keys and lists of slot objects.
    """
    slug = event_slug or config.CAL_EVENT_SLUG
    user = username or config.CAL_USERNAME

    params = {
        "eventTypeSlug": slug,
        "username": user,
        "start": start,
        "end": end,
        "timeZone": timezone,
    }

    url = f"{config.CAL_API_BASE}/slots"

    @tenacity.retry(
        retry=tenacity.retry_if_exception(_is_retryable),
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _do_fetch():
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params, headers=_headers(SLOTS_API_VERSION))
            resp.raise_for_status()
            return resp.json()

    data = await _do_fetch()
    return data.get("data", {})


async def create_booking(
    start: str,
    attendee_name: str,
    attendee_email: str,
    attendee_timezone: str = "Asia/Singapore",
    notes: Optional[str] = None,
    guests: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    event_type_id: Optional[int] = None,
) -> dict:
    """Create a booking via Cal.com API.

    Args:
        start: Start time in ISO 8601 format (UTC).
        attendee_name: Name of the person booking.
        attendee_email: Email of the person booking.
        attendee_timezone: IANA timezone of the attendee.
        notes: Optional notes for the meeting.
        guests: Optional list of guest email addresses.
        metadata: Optional metadata dict (source tracking, etc.).
        event_type_id: Cal.com event type ID (default from config).

    Returns:
        Cal.com booking response dict.
    """
    body: dict = {
        "eventTypeId": event_type_id or config.CAL_EVENT_TYPE_ID,
        "start": start,
        "attendee": {
            "name": attendee_name,
            "email": attendee_email,
            "timeZone": attendee_timezone,
        },
    }

    # Note: Cal.com v2 API no longer accepts "title" in the booking payload.
    # Calendar event titles are controlled via the eventName template on the event type
    # (configured via /api/v1/admin/fix-cal-titles endpoint).
    if notes:
        # Truncate to Cal.com's max character limit (defense in depth, frontend also limits)
        truncated = notes[:NOTES_MAX_CHARS]
        if len(notes) > NOTES_MAX_CHARS:
            logger.warning("Notes truncated from %d to %d chars", len(notes), NOTES_MAX_CHARS)
        body["bookingFieldsResponses"] = {"notes": truncated}
    if guests:
        body["guests"] = guests
    if metadata:
        body["metadata"] = metadata

    url = f"{config.CAL_API_BASE}/bookings"

    # Only send fields that Cal.com v2 currently accepts.
    # This prevents breakage if a previously-accepted field is removed.
    ALLOWED_FIELDS = {"eventTypeId", "start", "attendee", "bookingFieldsResponses", "guests", "metadata"}
    body = {k: v for k, v in body.items() if k in ALLOWED_FIELDS}

    @tenacity.retry(
        retry=tenacity.retry_if_exception(_is_retryable),
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _do_booking():
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=_headers(BOOKINGS_API_VERSION))
            if resp.status_code >= 400:
                logger.error("Cal.com booking error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()

    return await _do_booking()


async def get_event_type(event_type_id: int) -> dict:
    """Fetch a Cal.com event type's current settings (uses v1 API for eventName access)."""
    url = f"https://api.cal.com/v1/event-types/{event_type_id}"
    params = {"apiKey": config.CAL_API_KEY}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def update_event_type_title(event_type_id: int, event_name: str) -> dict:
    """Update the calendar event title template for a Cal.com event type.

    Uses Cal.com v1 API since v2 doesn't expose the eventName field.

    Args:
        event_type_id: Cal.com event type ID.
        event_name: Title template using Cal.com variables, e.g.
                     "{Scheduler} & Owner | Coffee Chat".
    """
    url = f"https://api.cal.com/v1/event-types/{event_type_id}"
    body = {"eventName": event_name}
    params = {"apiKey": config.CAL_API_KEY}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(url, json=body, params=params)
        if resp.status_code >= 400:
            logger.error("Cal.com event type update error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()
