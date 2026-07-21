from __future__ import annotations

import re


USERNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,30}[a-z0-9])$")
EMAIL_LOCAL_PATTERN = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
DOMAIN_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "api",
    "boardsight",
    "billing",
    "help",
    "root",
    "security",
    "support",
    "system",
}
RESERVED_EMAIL_DOMAINS = {"invalid", "localhost"}


def normalize_registration_username(value: str) -> str:
    username = str(value or "").strip().lower()
    if not 3 <= len(username) <= 32:
        raise ValueError("Username must contain between 3 and 32 characters.")
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username may use lowercase letters, numbers, dots, underscores, and hyphens, and must begin and end with a letter or number.")
    if re.search(r"[._-]{2}", username):
        raise ValueError("Username cannot contain consecutive punctuation characters.")
    if username in RESERVED_USERNAMES:
        raise ValueError("That username is reserved by BoardSight.")
    return username


def normalize_registration_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not email or len(email) > 254 or any(character.isspace() or ord(character) < 32 for character in email):
        raise ValueError("Enter a valid email address.")
    if email.count("@") != 1:
        raise ValueError("Enter a valid email address.")
    local_part, domain = email.rsplit("@", 1)
    if not local_part or len(local_part) > 64 or local_part.startswith(".") or local_part.endswith(".") or ".." in local_part:
        raise ValueError("Enter a valid email address.")
    if not EMAIL_LOCAL_PATTERN.fullmatch(local_part):
        raise ValueError("Enter a valid email address using standard email characters.")
    if domain in RESERVED_EMAIL_DOMAINS or domain.endswith(".local") or "." not in domain:
        raise ValueError("Enter a valid public email domain.")
    labels = domain.split(".")
    if any(not DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels):
        raise ValueError("Enter a valid email domain.")
    top_level_domain = labels[-1]
    if not (re.fullmatch(r"[a-z]{2,63}", top_level_domain) or top_level_domain.startswith("xn--")):
        raise ValueError("Enter a valid email domain.")
    return email


def validate_registration_display_name(value: str) -> str:
    display_name = " ".join(str(value or "").strip().split())
    if not 2 <= len(display_name) <= 80:
        raise ValueError("Display name must contain between 2 and 80 characters.")
    if any(ord(character) < 32 for character in display_name):
        raise ValueError("Display name contains unsupported characters.")
    return display_name
