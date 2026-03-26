"""Shared test fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Set minimal env vars so config module loads without real credentials."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("BOOKING_API_KEY", "test-api-key-12345")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("CAL_API_KEY", "cal_test_key")
    monkeypatch.setenv("CAL_USERNAME", "testuser")
    monkeypatch.setenv("BASE_URL", "https://book.test.com")
    monkeypatch.setenv("OWNER_NAME", "Test Owner")
    monkeypatch.setenv("OWNER_FIRST_NAME", "Test")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com,https://other.com")
