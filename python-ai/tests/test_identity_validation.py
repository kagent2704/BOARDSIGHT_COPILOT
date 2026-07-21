from __future__ import annotations

import pytest

from boardsight_ai.identity_validation import normalize_registration_email, normalize_registration_username, validate_registration_display_name


@pytest.mark.parametrize("value", ["ab", "admin", "bad name", "-leading", "trailing-", "two..dots", "name@example"])
def test_registration_username_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_registration_username(value)


@pytest.mark.parametrize("value", ["missing-at.example.com", "a@localhost", ".start@gmail.com", "double..dot@gmail.com", "user@-bad.com", "user@example.c"])
def test_registration_email_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_registration_email(value)


def test_registration_identity_values_are_normalized() -> None:
    assert normalize_registration_username("  Kashmira.Patil  ") == "kashmira.patil"
    assert normalize_registration_email("  KashmiraPatil@GMAIL.COM ") == "kashmirapatil@gmail.com"
    assert validate_registration_display_name("  Kashmira   Patil  ") == "Kashmira Patil"
