"""Tests for utility/helper functions in routes.py."""

import re
import time
from collections import defaultdict
from unittest.mock import patch, MagicMock

import pytest


# --- Slug generation (extracted logic, no DB dependency) ---


def _slugify_pure(name: str) -> str:
    """Pure slug generation without DB collision check (mirrors routes._slugify logic)."""
    transliterations = {
        "u\u0308": "ue", "o\u0308": "oe", "a\u0308": "ae", "\u00df": "ss",
        "\u00fc": "ue", "\u00f6": "oe", "\u00e4": "ae",
        "\u00e9": "e", "\u00e8": "e", "\u00ea": "e", "\u00eb": "e",
        "\u00e1": "a", "\u00e0": "a", "\u00e2": "a", "\u00e3": "a",
        "\u00ed": "i", "\u00ec": "i", "\u00ee": "i", "\u00ef": "i",
        "\u00f3": "o", "\u00f2": "o", "\u00f4": "o", "\u00f5": "o",
        "\u00fa": "u", "\u00f9": "u", "\u00fb": "u",
        "\u00f1": "n", "\u00e7": "c",
    }
    slug = name.lower().strip()
    for char, replacement in transliterations.items():
        slug = slug.replace(char, replacement)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


class TestSlugGeneration:
    def test_basic_name(self):
        assert _slugify_pure("John Smith") == "john-smith"

    def test_extra_whitespace(self):
        assert _slugify_pure("  John   Smith  ") == "john-smith"

    def test_german_umlauts(self):
        assert _slugify_pure("M\u00fcller") == "mueller"
        assert _slugify_pure("Sch\u00f6n") == "schoen"
        assert _slugify_pure("J\u00e4ger") == "jaeger"

    def test_sharp_s(self):
        assert _slugify_pure("Stra\u00dfe") == "strasse"

    def test_french_accents(self):
        assert _slugify_pure("Ren\u00e9 Fran\u00e7ois") == "rene-francois"

    def test_spanish_tilde(self):
        assert _slugify_pure("Se\u00f1or Nu\u00f1ez") == "senor-nunez"

    def test_portuguese_accents(self):
        assert _slugify_pure("Jo\u00e3o") == "joao"

    def test_special_characters_stripped(self):
        assert _slugify_pure("O'Brien-Smith") == "o-brien-smith"

    def test_numbers_preserved(self):
        assert _slugify_pure("Agent 007") == "agent-007"

    def test_empty_string(self):
        assert _slugify_pure("") == ""

    def test_only_special_chars(self):
        assert _slugify_pure("!!!@@@###") == ""

    def test_mixed_case(self):
        assert _slugify_pure("UPPER lower MiXeD") == "upper-lower-mixed"


# --- HTML escaping ---


def _escape_html(text: str) -> str:
    """Mirror of routes._escape_html."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


class TestEscapeHtml:
    def test_ampersand(self):
        assert _escape_html("A & B") == "A &amp; B"

    def test_angle_brackets(self):
        assert _escape_html("<script>alert('xss')</script>") == (
            "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        )

    def test_quotes(self):
        assert _escape_html('He said "hello"') == "He said &quot;hello&quot;"

    def test_single_quotes(self):
        assert _escape_html("it's") == "it&#x27;s"

    def test_no_escape_needed(self):
        assert _escape_html("plain text") == "plain text"

    def test_empty_string(self):
        assert _escape_html("") == ""

    def test_all_special_chars(self):
        result = _escape_html("&<>\"'")
        assert "&" not in result or "&amp;" in result
        assert "<" not in result.replace("&lt;", "")
        assert ">" not in result.replace("&gt;", "")

    def test_double_ampersand(self):
        """Ensure & in already-escaped text gets re-escaped."""
        assert _escape_html("&amp;") == "&amp;amp;"


# --- JS escaping ---


def _escape_js(text: str) -> str:
    """Mirror of routes._escape_js."""
    return (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("/", "\\/")
    )


class TestEscapeJs:
    def test_single_quotes(self):
        assert _escape_js("it's") == "it\\'s"

    def test_double_quotes(self):
        assert _escape_js('say "hi"') == 'say \\"hi\\"'

    def test_backslashes(self):
        assert _escape_js("path\\to\\file") == "path\\\\to\\\\file"

    def test_newlines(self):
        assert _escape_js("line1\nline2") == "line1\\nline2"

    def test_carriage_return(self):
        assert _escape_js("line1\rline2") == "line1\\rline2"

    def test_script_breakout(self):
        """Ensure </script> cannot break out of a JS string context."""
        result = _escape_js("</script>")
        assert "</script>" not in result
        assert "<\\/script>" in result

    def test_empty_string(self):
        assert _escape_js("") == ""

    def test_no_escape_needed(self):
        assert _escape_js("plain text") == "plain text"


# --- Rate limiting ---


def _check_rate_limit(
    rate_limits: dict,
    client_ip: str,
    window: int = 300,
    max_attempts: int = 5,
) -> bool:
    """Mirror of routes._check_rate_limit with injectable state."""
    now = time.time()
    key_attempts = rate_limits[client_ip]
    rate_limits[client_ip] = [t for t in key_attempts if now - t < window]
    if len(rate_limits[client_ip]) >= max_attempts:
        return False
    rate_limits[client_ip].append(now)
    return True


class TestRateLimit:
    def test_allows_first_request(self):
        limits = defaultdict(list)
        assert _check_rate_limit(limits, "1.2.3.4") is True

    def test_allows_up_to_max(self):
        limits = defaultdict(list)
        for _ in range(5):
            assert _check_rate_limit(limits, "1.2.3.4") is True

    def test_blocks_over_max(self):
        limits = defaultdict(list)
        for _ in range(5):
            _check_rate_limit(limits, "1.2.3.4")
        assert _check_rate_limit(limits, "1.2.3.4") is False

    def test_separate_ips(self):
        limits = defaultdict(list)
        for _ in range(5):
            _check_rate_limit(limits, "1.1.1.1")
        # Different IP should still be allowed
        assert _check_rate_limit(limits, "2.2.2.2") is True

    def test_expired_entries_cleared(self):
        limits = defaultdict(list)
        # Add entries that are already expired (in the past)
        limits["1.2.3.4"] = [time.time() - 400] * 5  # older than 300s window
        assert _check_rate_limit(limits, "1.2.3.4") is True

    def test_custom_window_and_max(self):
        limits = defaultdict(list)
        for _ in range(3):
            _check_rate_limit(limits, "1.2.3.4", window=60, max_attempts=3)
        assert _check_rate_limit(limits, "1.2.3.4", window=60, max_attempts=3) is False


# --- Crawler detection ---


_CRAWLER_KEYWORDS = (
    "whatsapp", "telegrambot", "facebookexternalhit", "facebot",
    "linkedinbot", "twitterbot", "slackbot", "discordbot",
    "googlebot", "bingbot", "applebot", "iframely", "embedly",
    "preview", "crawler", "spider", "bot/",
)


def _is_crawler(user_agent: str) -> bool:
    """Check if user-agent matches a known crawler."""
    ua = user_agent.lower()
    return any(kw in ua for kw in _CRAWLER_KEYWORDS)


class TestCrawlerDetection:
    def test_whatsapp(self):
        assert _is_crawler("WhatsApp/2.23.20.0") is True

    def test_telegram(self):
        assert _is_crawler("TelegramBot (like TwitterBot)") is True

    def test_linkedin(self):
        assert _is_crawler("LinkedInBot/1.0") is True

    def test_facebook(self):
        assert _is_crawler("facebookexternalhit/1.1") is True

    def test_google(self):
        assert _is_crawler("Googlebot/2.1") is True

    def test_regular_browser(self):
        assert _is_crawler("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)") is False

    def test_empty_ua(self):
        assert _is_crawler("") is False

    def test_case_insensitive(self):
        assert _is_crawler("WHATSAPP/2.0") is True
