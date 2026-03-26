"""Tests for configuration and constants."""

import pytest


class TestConfig:
    """Test that config loads correctly from environment."""

    def test_config_loads(self):
        from app.config import config
        assert config.OWNER_NAME == "Test Owner"
        assert config.OWNER_FIRST_NAME == "Test"
        assert config.BASE_URL == "https://book.test.com"
        assert config.CAL_USERNAME == "testuser"

    def test_meeting_types_complete(self):
        from app.config import config
        required_keys = {"quick_call", "discovery_call", "coffee_chat", "extended_call", "deep_dive", "none"}
        assert set(config.MEETING_TYPES.keys()) == required_keys

    def test_meeting_type_structure(self):
        from app.config import config
        for key, mt in config.MEETING_TYPES.items():
            assert "event_type_id" in mt, f"{key} missing event_type_id"
            assert "slug" in mt, f"{key} missing slug"
            assert "label" in mt, f"{key} missing label"
            assert "duration" in mt, f"{key} missing duration"
            assert isinstance(mt["duration"], int), f"{key} duration should be int"

    def test_default_meeting_type_exists(self):
        from app.config import config
        assert config.DEFAULT_MEETING_TYPE in config.MEETING_TYPES


class TestCalClientConstants:
    """Test Cal.com client constants."""

    def test_api_versions_set(self):
        from app.cal_client import SLOTS_API_VERSION, BOOKINGS_API_VERSION, EVENT_TYPES_API_VERSION
        assert SLOTS_API_VERSION
        assert BOOKINGS_API_VERSION
        assert EVENT_TYPES_API_VERSION

    def test_notes_max_chars(self):
        from app.cal_client import NOTES_MAX_CHARS
        assert NOTES_MAX_CHARS > 0
        assert NOTES_MAX_CHARS <= 1000  # sanity check


class TestRetryLogic:
    """Test the retry predicate for Cal.com client."""

    def test_timeout_is_retryable(self):
        import httpx
        from app.cal_client import _is_retryable
        assert _is_retryable(httpx.TimeoutException("timeout")) is True

    def test_500_is_retryable(self):
        import httpx
        from app.cal_client import _is_retryable
        response = httpx.Response(500)
        exc = httpx.HTTPStatusError("server error", request=httpx.Request("GET", "http://x"), response=response)
        assert _is_retryable(exc) is True

    def test_400_is_not_retryable(self):
        import httpx
        from app.cal_client import _is_retryable
        response = httpx.Response(400)
        exc = httpx.HTTPStatusError("bad request", request=httpx.Request("GET", "http://x"), response=response)
        assert _is_retryable(exc) is False

    def test_value_error_is_not_retryable(self):
        from app.cal_client import _is_retryable
        assert _is_retryable(ValueError("nope")) is False
