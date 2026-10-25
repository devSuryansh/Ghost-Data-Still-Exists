"""Shared observation schema for evidence parsers."""

from dataclasses import dataclass, field


CATEGORY_SYSTEM = {
    "USER_PROFILE": "account_service",
    "SECONDARY_IDENTIFIER": "account_service",
    "SEARCH_INDEX_ENTRY": "search_service",
    "CACHE_ENTRY": "cache_service",
    "SUPPORT_MESSAGE": "support_platform",
    "SUPPORT_ATTACHMENT": "support_platform",
    "ANALYTICS_PROFILE": "analytics_platform",
    "PRODUCT_TELEMETRY": "analytics_platform",
    "USER_EXPORT": "export_service",
    "MARKETING_PROFILE": "marketing_platform",
    "EMAIL_DELIVERY_LOG": "email_delivery_service",
    "SECURITY_AUDIT_LOG": "security_service",
    "LEGAL_HOLD_RECORD": "legal_service",
    "BACKUP_ARCHIVE": "backup_service",
    "ACCOUNT_TOMBSTONE": "identity_service",
    "DATA_FLOW": "integration_service",
}

# Default policy action for a category. DATA_FLOW and BACKUP are process rules.
CATEGORY_ACTION = {
    "USER_PROFILE": "DELETE",
    "SECONDARY_IDENTIFIER": "DELETE",
    "SEARCH_INDEX_ENTRY": "DELETE",
    "CACHE_ENTRY": "DELETE",
    "SUPPORT_MESSAGE": "REDACT",
    "SUPPORT_ATTACHMENT": "DELETE",
    "ANALYTICS_PROFILE": "ANONYMIZE",
    "PRODUCT_TELEMETRY": "ANONYMIZE",
    "USER_EXPORT": "DELETE",
    "MARKETING_PROFILE": "DELETE",
    "EMAIL_DELIVERY_LOG": "REDACT",
    "SECURITY_AUDIT_LOG": "RETAIN",
    "LEGAL_HOLD_RECORD": "RETAIN",
    "BACKUP_ARCHIVE": "BACKUP",
    "ACCOUNT_TOMBSTONE": "REDACT",
    "DATA_FLOW": "FLOW",
}

PREFIX_CATEGORY = (
    ("audit_record_", "SECURITY_AUDIT_LOG"),
    ("email_delivery_", "EMAIL_DELIVERY_LOG"),
    ("data_flow_", "DATA_FLOW"),
    ("tombstone_", "ACCOUNT_TOMBSTONE"),
    ("analytics_", "ANALYTICS_PROFILE"),
    ("marketing_", "MARKETING_PROFILE"),
    ("telemetry_", "PRODUCT_TELEMETRY"),
    ("account_", "USER_PROFILE"),
    ("search_", "SEARCH_INDEX_ENTRY"),
    ("support_", "SUPPORT_MESSAGE"),
    ("backup_", "BACKUP_ARCHIVE"),
    ("export_", "USER_EXPORT"),
    ("cache_", "CACHE_ENTRY"),
    ("object_", "SUPPORT_ATTACHMENT"),
    ("legal_", "LEGAL_HOLD_RECORD"),
)

NULL_TOKENS = {
    "",
    "null",
    "none",
    "nil",
    "n/a",
    "na",
    "no direct identifier",
    "-",
}


@dataclass
class Observation:
    evidence_id: str
    manifest_at: str
    observed_at: str
    system_id: str
    resource_id: str
    category: str
    topology: str
    present: bool | None
    link_ids: set[str] = field(default_factory=set)
    direct_pii: bool = False
    attributable: bool = False
    enabled: bool | None = None
    restore_allowed: bool | None = None
    retention_until: str | None = None
    legal_active: bool | None = None
    action_override: str | None = None
    source_ids: set[str] = field(default_factory=set)
    cohort: str = ""

    def action(self) -> str:
        if self.action_override:
            return self.action_override
        return CATEGORY_ACTION.get(self.category, "DELETE")


@dataclass
class Activity:
    activity_id: str
    event_time: str
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str
    link_ids: set[str] = field(default_factory=set)


@dataclass
class CollectionScan:
    """A captured collection, including an empty one."""

    evidence_id: str
    manifest_at: str
    observed_at: str
    system_id: str
    category: str
    present_ids: set[str] = field(default_factory=set)


@dataclass
class Gap:
    evidence_id: str
    path: str
    reason: str


def category_for_resource(resource_id: str, record_type: str | None = None) -> str:
    if record_type:
        token = record_type.strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "DATA_FLOW": "DATA_FLOW",
            "USER_PROFILE": "USER_PROFILE",
            "SEARCH_INDEX_ENTRY": "SEARCH_INDEX_ENTRY",
            "ANALYTICS_PROFILE": "ANALYTICS_PROFILE",
            "SUPPORT_MESSAGE": "SUPPORT_MESSAGE",
            "SUPPORT_ATTACHMENT": "SUPPORT_ATTACHMENT",
            "USER_EXPORT": "USER_EXPORT",
            "BACKUP_ARCHIVE": "BACKUP_ARCHIVE",
            "SECURITY_AUDIT_LOG": "SECURITY_AUDIT_LOG",
            "ACCOUNT_TOMBSTONE": "ACCOUNT_TOMBSTONE",
            "CACHE_ENTRY": "CACHE_ENTRY",
            "MARKETING_PROFILE": "MARKETING_PROFILE",
            "EMAIL_DELIVERY_LOG": "EMAIL_DELIVERY_LOG",
            "LEGAL_HOLD_RECORD": "LEGAL_HOLD_RECORD",
            "PRODUCT_TELEMETRY": "PRODUCT_TELEMETRY",
            "SECONDARY_IDENTIFIER": "SECONDARY_IDENTIFIER",
        }
        if token in aliases:
            return aliases[token]
    for prefix, category in PREFIX_CATEGORY:
        if resource_id.startswith(prefix):
            return category
    return "USER_PROFILE"


def system_for(category: str, explicit: str | None = None) -> str:
    if explicit and explicit.endswith("_service") or (explicit and explicit.endswith("_platform")):
        return explicit
    known = {
        "account_service",
        "search_service",
        "support_platform",
        "analytics_platform",
        "security_service",
        "integration_service",
        "backup_service",
        "export_service",
        "identity_service",
        "cache_service",
        "marketing_platform",
        "email_delivery_service",
        "legal_service",
        "object_storage",
        "profile_service",
    }
    if explicit in known:
        if explicit == "profile_service":
            return "account_service"
        return explicit
    return CATEGORY_SYSTEM.get(category, explicit or "account_service")
