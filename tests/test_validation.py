"""Tests for Pydantic model validation."""

import pytest
from pydantic import ValidationError


# We test the models by importing them. Since they depend on app.config,
# the conftest fixture sets env vars before import.


class TestInviteCreateValidation:
    """Test InviteCreate Pydantic model."""

    def _model(self):
        from app.routes import InviteCreate
        return InviteCreate

    def test_minimal_valid(self):
        Model = self._model()
        invite = Model(
            recipient_name="John Smith",
            recipient_first_name="John",
        )
        assert invite.recipient_name == "John Smith"
        assert invite.greeting == "A note for"
        assert invite.expires_days == 30

    def test_full_valid(self):
        Model = self._model()
        invite = Model(
            recipient_name="John Smith",
            recipient_first_name="John",
            recipient_email="john@example.com",
            contact_id="abc-123",
            greeting="Hey there",
            context_quote="We met at the conference",
            closing="Talk soon!",
            cal_link="testuser/coffee-chat",
            duration_minutes=30,
            og_title="Custom OG title",
            og_description="Custom OG desc",
            expires_days=14,
            meeting_type="coffee_chat",
        )
        assert invite.meeting_type == "coffee_chat"
        assert invite.expires_days == 14

    def test_missing_required_fields(self):
        Model = self._model()
        with pytest.raises(ValidationError) as exc_info:
            Model()
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "recipient_name" in field_names
        assert "recipient_first_name" in field_names

    def test_optional_fields_default_none(self):
        Model = self._model()
        invite = Model(
            recipient_name="Jane Doe",
            recipient_first_name="Jane",
        )
        assert invite.recipient_email is None
        assert invite.contact_id is None
        assert invite.context_quote is None
        assert invite.meeting_type is None


class TestInviteUpdateValidation:
    """Test InviteUpdate Pydantic model."""

    def _model(self):
        from app.routes import InviteUpdate
        return InviteUpdate

    def test_empty_update(self):
        Model = self._model()
        update = Model()
        assert update.status is None
        assert update.context_quote is None

    def test_status_update(self):
        Model = self._model()
        update = Model(status="booked")
        assert update.status == "booked"

    def test_partial_update(self):
        Model = self._model()
        update = Model(context_quote="New context", closing="New closing")
        assert update.context_quote == "New context"
        assert update.status is None


class TestBookingRequestValidation:
    """Test BookingRequest Pydantic model."""

    def _model(self):
        from app.routes import BookingRequest
        return BookingRequest

    def test_minimal_valid(self):
        Model = self._model()
        req = Model(
            start="2026-04-01T10:00:00Z",
            name="John Smith",
            email="john@example.com",
        )
        assert req.timezone == "Asia/Singapore"
        assert req.notes is None
        assert req.guests is None

    def test_with_guests(self):
        Model = self._model()
        req = Model(
            start="2026-04-01T10:00:00Z",
            name="John Smith",
            email="john@example.com",
            guests=["guest1@example.com", "guest2@example.com"],
        )
        assert len(req.guests) == 2

    def test_too_many_guests(self):
        Model = self._model()
        with pytest.raises(ValidationError) as exc_info:
            Model(
                start="2026-04-01T10:00:00Z",
                name="John Smith",
                email="john@example.com",
                guests=[f"guest{i}@example.com" for i in range(6)],
            )
        assert "Maximum 5" in str(exc_info.value)

    def test_invalid_guest_email(self):
        Model = self._model()
        with pytest.raises(ValidationError) as exc_info:
            Model(
                start="2026-04-01T10:00:00Z",
                name="John Smith",
                email="john@example.com",
                guests=["not-an-email"],
            )
        assert "Invalid guest email" in str(exc_info.value)

    def test_missing_required_fields(self):
        Model = self._model()
        with pytest.raises(ValidationError) as exc_info:
            Model()
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "start" in field_names
        assert "name" in field_names
        assert "email" in field_names


class TestAdminLoginValidation:
    """Test AdminLogin Pydantic model."""

    def _model(self):
        from app.routes import AdminLogin
        return AdminLogin

    def test_valid(self):
        Model = self._model()
        login = Model(password="secret")
        assert login.password == "secret"

    def test_missing_password(self):
        Model = self._model()
        with pytest.raises(ValidationError):
            Model()
