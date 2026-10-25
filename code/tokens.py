"""Exact identifier extraction. Substring lookalikes are not matches."""

import re

EMAIL_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._%+\-]*@[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}"
)
USER_RE = re.compile(r"(?<![A-Za-z0-9_])user_\d+(?![A-Za-z0-9_])")
HASH_RE = re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{64}(?![A-Za-z0-9])")
RESOURCE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"audit_record|email_delivery|data_flow|tombstone|analytics|marketing|"
    r"telemetry|account|search|support|backup|export|cache|object|legal"
    r")_[A-Za-z0-9]+(?![A-Za-z0-9_])"
)

NULL_TEXT = {
    "",
    "null",
    "none",
    "nil",
    "n/a",
    "na",
    "no direct identifier",
    "-",
    "redacted",
    "anonymized",
}


def clean_token(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("\"'")
    if text.casefold() in NULL_TEXT:
        return None
    if text.lower() in {"true", "false"}:
        return None
    return text


def norm_email(value: str) -> str:
    return value.strip().casefold()


def norm_hash(value: str) -> str:
    return value.strip().casefold()


def emails_in(text: str) -> set[str]:
    return {norm_email(match) for match in EMAIL_RE.findall(text or "")}


def users_in(text: str) -> set[str]:
    return set(USER_RE.findall(text or ""))


def hashes_in(text: str) -> set[str]:
    return {norm_hash(match) for match in HASH_RE.findall(text or "")}


def resources_in(text: str) -> set[str]:
    return set(RESOURCE_RE.findall(text or ""))


def link_ids_in_text(text: str) -> set[str]:
    found: set[str] = set()
    found.update(emails_in(text))
    found.update(users_in(text))
    found.update(hashes_in(text))
    return found


def add_link_id(bucket: set[str], value: str | None, kind: str) -> None:
    token = clean_token(value)
    if not token:
        return
    if kind == "email":
        if EMAIL_RE.fullmatch(token):
            bucket.add(norm_email(token))
        return
    if kind == "user":
        if USER_RE.fullmatch(token):
            bucket.add(token)
        return
    if kind == "hash":
        if HASH_RE.fullmatch(token):
            bucket.add(norm_hash(token))
        return
    if kind == "phone":
        bucket.add(token)
        return
    if kind == "name":
        if "@" in token or token.startswith("user_"):
            return
        if len(token) < 3:
            return
        bucket.add("name:" + token.casefold())
