"""Build observations from structured fields."""

from code.schema import Observation, category_for_resource, system_for
from code.tokens import add_link_id, clean_token, emails_in, link_ids_in_text, resources_in

LINK_FIELDS = {
    "email": "email",
    "owner_email": "email",
    "customer_email": "email",
    "requester_email": "email",
    "phone": "phone",
    "owner_phone": "phone",
    "requester_phone": "phone",
    "email_hash": "hash",
    "user_id": "user",
    "customer_reference": "user",
    "subject_reference": "auto",
    "subject_ref": "auto",
    "lookup_key": "auto",
    "lookup_value": "auto",
    "match_key": "auto",
    "correlation_key": "auto",
    "query": "auto",
    "subject_key": "auto",
    "matched_value": "auto",
    "name": "name",
    "full_name": "name",
    "display_name": "name",
    "requester_name": "name",
}

STORED_PII_FIELDS = {
    "email",
    "owner_email",
    "customer_email",
    "requester_email",
    "phone",
    "owner_phone",
    "requester_phone",
    "email_hash",
    "name",
    "full_name",
    "display_name",
    "requester_name",
}

STORED_ATTR_FIELDS = STORED_PII_FIELDS | {
    "user_id",
    "customer_reference",
    "subject_reference",
}


def _as_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "enabled", "active"}:
        return True
    if text in {"0", "false", "no", "disabled", "blocked"}:
        return False
    return None


def _auto_kind(value: str) -> str:
    token = value.strip()
    if "@" in token:
        return "email"
    if token.startswith("user_"):
        return "user"
    if len(token) == 64:
        return "hash"
    return "skip"


def fields_from_mapping(data: dict) -> dict:
    flat: dict = {}
    for key, value in data.items():
        if isinstance(value, dict):
            if "resource_id" in value:
                continue
            for inner_key, inner_value in value.items():
                if not isinstance(inner_value, (dict, list)):
                    flat.setdefault(inner_key, inner_value)
        elif isinstance(value, list):
            continue
        else:
            flat[key] = value
    return flat


def make_observation(
    *,
    evidence_id: str,
    manifest_at: str,
    observed_at: str,
    resource_id: str,
    fields: dict,
    explicit_system: str | None = None,
    record_type: str | None = None,
    topology: str = "primary",
    event_name: str | None = None,
    extra_link_ids: set[str] | None = None,
) -> Observation | None:
    if not resource_id or resource_id.startswith("tr-"):
        return None
    fields = fields_from_mapping(fields)
    category = category_for_resource(resource_id, record_type or fields.get("record_type"))
    system = system_for(category, explicit_system or _text(fields.get("system")) or _text(fields.get("service")))
    result = _text(fields.get("result"))
    result_fold = result.casefold() if result else ""
    event = (event_name or _text(fields.get("event")) or "").casefold()
    present = _present_from_fields(fields, result_fold)
    link_ids: set[str] = set()
    stored_pii = False
    attributable = False
    for key, kind in LINK_FIELDS.items():
        raw = fields.get(key)
        if raw is None:
            continue
        text = _text(raw)
        if text is None:
            continue
        use_kind = kind
        if kind == "auto":
            use_kind = _auto_kind(text)
            if use_kind == "skip":
                link_ids.update(link_ids_in_text(text))
                continue
        before = set(link_ids)
        add_link_id(link_ids, text, use_kind)
        added = link_ids - before
        if added and key in STORED_PII_FIELDS and result_fold not in {"not_found", "anonymized", "redacted"}:
            stored_pii = True
        if added and key in STORED_ATTR_FIELDS and result_fold not in {"not_found", "anonymized", "redacted"}:
            attributable = True

    if extra_link_ids:
        link_ids.update(extra_link_ids)
    message = " ".join(
        str(fields.get(key) or "")
        for key in ("message_text", "message_excerpt", "message")
    )
    message_emails = emails_in(message)
    if message_emails and result_fold not in {"anonymized", "redacted", "not_found"}:
        stored_pii = True
        attributable = True
        if not link_ids:
            link_ids.update(message_emails)

    if result_fold == "anonymized":
        stored_pii = False
        attributable = False
    if result_fold == "redacted":
        stored_pii = False
    if result_fold in {"not_found", "miss"}:
        stored_pii = False
        attributable = False

    enabled = _as_bool(fields.get("enabled"))
    restore_allowed = _as_bool(fields.get("restore_allowed"))
    if "deletion_block" in fields or "eligible" in fields:
        blocked = _as_bool(fields.get("deletion_block"))
        eligible = _as_bool(fields.get("eligible"))
        if blocked is True:
            restore_allowed = False
        elif eligible is True and blocked is False:
            restore_allowed = True
    if result_fold == "active" and category == "BACKUP_ARCHIVE":
        restore_allowed = True
    if result_fold == "blocked" and category == "BACKUP_ARCHIVE":
        restore_allowed = False
    if result_fold == "active" and category == "DATA_FLOW":
        enabled = True
    if result_fold == "disabled" and category == "DATA_FLOW":
        enabled = False

    action_override = None
    if "pii_scan" in event or fields.get("matched_value"):
        stored_pii = True
        attributable = True
        if present is None:
            present = True
    if "contact_lookup" in event or "contact_query" in event:
        action_override = "DELETE"
        present = True if present is None else present
    if "attachment" in event or category == "SUPPORT_ATTACHMENT":
        action_override = "DELETE"
    if result_fold == "identifiable" and category == "ANALYTICS_PROFILE":
        stored_pii = True
        attributable = True
    if result_fold == "identifiable" and category in {"SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT"}:
        stored_pii = True
        attributable = True

    retention = _text(fields.get("retention_until"))
    legal_active = _as_bool(fields.get("legal_hold_active"))
    if category == "LEGAL_HOLD_RECORD" and legal_active is None:
        legal_active = True if present else None

    source_ids = resources_in(_text(fields.get("source_resource_id")) or "")
    source_ids.discard(resource_id)

    return Observation(
        evidence_id=evidence_id,
        manifest_at=manifest_at,
        observed_at=observed_at or manifest_at,
        system_id=system,
        resource_id=resource_id,
        category=category,
        topology=topology or "primary",
        present=present,
        link_ids=link_ids,
        direct_pii=stored_pii,
        attributable=attributable or stored_pii,
        enabled=enabled,
        restore_allowed=restore_allowed,
        retention_until=retention,
        legal_active=legal_active,
        action_override=action_override,
        source_ids=source_ids,
    )


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    return clean_token(str(value))


def _present_from_fields(fields: dict, result_fold: str) -> bool | None:
    rows_present = None
    if fields.get("rows") is not None:
        try:
            rows_present = int(fields["rows"]) > 0
        except (TypeError, ValueError):
            rows_present = None
    if rows_present is True:
        return True
    if result_fold in {"not_found", "miss", "absent", "deleted"}:
        return False
    if result_fold in {
        "found",
        "hit",
        "identifiable",
        "anonymized",
        "redacted",
        "active",
        "blocked",
        "disabled",
        "present",
    }:
        return True
    status = fields.get("status_code", fields.get("http_status"))
    if status is not None:
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = None
        if code == 404:
            return False
        if code is not None and 200 <= code < 300:
            return True
    if rows_present is False:
        return False
    event_name = str(fields.get("event") or "")
    if event_name.endswith("_started") and rows_present is None and status is None and not result_fold:
        return None
    if "profile" in fields and fields.get("profile") is None and status is None:
        return None
    if fields.get("download_available") is True:
        return True
    # A stored row with a resource id and no negative marker is present.
    return True
