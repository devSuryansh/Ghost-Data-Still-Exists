"""Current and historical identifier sets for a deletion subject."""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from code.tokens import add_link_id, clean_token, norm_email, norm_hash


@dataclass
class Subject:
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    link_ids: set[str] = field(default_factory=set)


class IdentityIndex:
    def __init__(self, subjects: dict[str, Subject], by_token: dict[str, set[str]]):
        self.subjects = subjects
        self.by_token = by_token

    def subject_for_email(self, email: str) -> Subject | None:
        matches = self.by_token.get(norm_email(email), set())
        if len(matches) != 1:
            return None
        return self.subjects[next(iter(matches))]

    def users_for_tokens(self, tokens: set[str]) -> set[str]:
        found: set[str] = set()
        for token in tokens:
            found.update(self.by_token.get(token, set()))
        return found


def _add_unique(index: dict[str, set[str]], token: str, user_id: str) -> None:
    index.setdefault(token, set()).add(user_id)


def load_identities(dataset: Path) -> IdentityIndex:
    subjects: dict[str, Subject] = {}
    by_token: dict[str, set[str]] = {}
    with (dataset / "user_identities.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            link_ids: set[str] = set()
            add_link_id(link_ids, row.get("email"), "email")
            add_link_id(link_ids, row.get("phone"), "phone")
            add_link_id(link_ids, row.get("email_hash"), "hash")
            add_link_id(link_ids, row.get("user_id"), "user")
            add_link_id(link_ids, row.get("name"), "name")
            subject = Subject(
                user_id=row["user_id"],
                name=row.get("name") or "",
                email=row.get("email") or "",
                phone=row.get("phone") or "",
                email_hash=row.get("email_hash") or "",
                link_ids=set(link_ids),
            )
            subjects[subject.user_id] = subject
            for token in link_ids:
                _add_unique(by_token, token, subject.user_id)

    field_kind = {
        "email": "email",
        "phone": "phone",
        "email_hash": "hash",
        "name": "name",
    }
    audit_path = dataset / "user_audit_log.csv"
    if audit_path.exists():
        with audit_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                kind = field_kind.get(row.get("field_name", ""))
                user_id = row.get("user_id")
                if not kind or user_id not in subjects:
                    continue
                for column in ("old_value", "new_value"):
                    token_set: set[str] = set()
                    add_link_id(token_set, row.get(column), kind)
                    for token in token_set:
                        subjects[user_id].link_ids.add(token)
                        _add_unique(by_token, token, user_id)

    # Names and other weak tokens that hit more than one person are not links.
    ambiguous = [token for token, users in by_token.items() if len(users) > 1]
    for token in ambiguous:
        users = by_token.pop(token)
        for user_id in users:
            subjects[user_id].link_ids.discard(token)

    # Keep hash normalization stable if a raw hash slipped through.
    extra: dict[str, set[str]] = {}
    for token, users in list(by_token.items()):
        if len(token) == 64:
            folded = norm_hash(token)
            if folded != token:
                extra.setdefault(folded, set()).update(users)
    by_token.update(extra)
    return IdentityIndex(subjects, by_token)


def canonical_account_id(user_id: str) -> str | None:
    """Account id used when the profile number is the same as the user number."""
    prefix = "user_"
    if not user_id.startswith(prefix):
        return None
    suffix = user_id[len(prefix):]
    if not suffix.isdigit():
        return None
    number = int(suffix)
    if number < 1000:
        return f"account_{number:03d}"
    return f"account_{number}"


def request_email_token(email: str) -> str:
    token = clean_token(email)
    if not token:
        return ""
    return norm_email(token)
