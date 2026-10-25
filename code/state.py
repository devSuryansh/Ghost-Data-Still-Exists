"""Resource state at a case cutoff. Replica copies stay until a later copy replaces them."""

from dataclasses import dataclass

from code.schema import CATEGORY_ACTION, CollectionScan, Observation


def evidence_number(evidence_id: str) -> int:
    digits = "".join(character for character in evidence_id if character.isdigit())
    return int(digits) if digits else 0


@dataclass
class Resolved:
    resource_id: str
    system_id: str
    category: str
    action: str
    present: bool
    direct_pii: bool
    attributable: bool
    enabled: bool | None
    restore_allowed: bool | None
    retention_until: str | None
    legal_active: bool | None
    evidence_id: str
    observed_at: str


def _admissible(obs: Observation, audit_at: str) -> bool:
    return obs.observed_at <= audit_at


def _citable(obs: Observation, audit_at: str) -> bool:
    return obs.manifest_at <= audit_at and obs.observed_at <= audit_at


def _later(obs: Observation, previous: Observation | None) -> bool:
    if previous is None:
        return True
    return (obs.observed_at, evidence_number(obs.evidence_id)) >= (
        previous.observed_at,
        evidence_number(previous.evidence_id),
    )


def resolve_resource(
    resource_id: str,
    observations: list[Observation],
    audit_at: str,
) -> Resolved | None:
    admissible = [obs for obs in observations if obs.resource_id == resource_id and _admissible(obs, audit_at)]
    if not admissible:
        return None
    copies: dict[str, Observation] = {}
    for obs in admissible:
        current = copies.get(obs.topology)
        if _later(obs, current):
            copies[obs.topology] = obs
    present_copies = [obs for obs in copies.values() if obs.present]
    absent_copies = [obs for obs in copies.values() if obs.present is False]
    base = present_copies[0] if present_copies else (absent_copies[0] if absent_copies else admissible[-1])
    present = bool(present_copies)
    direct_pii = any(obs.direct_pii for obs in present_copies)
    attributable = any(obs.attributable or obs.direct_pii for obs in present_copies)
    enabled_values = [obs.enabled for obs in present_copies if obs.enabled is not None]
    restore_values = [obs.restore_allowed for obs in present_copies if obs.restore_allowed is not None]
    enabled = True if any(enabled_values) else (False if enabled_values else None)
    restore_allowed = True if any(restore_values) else (False if restore_values else None)
    retention = None
    for obs in sorted(present_copies or absent_copies, key=lambda item: item.observed_at):
        if obs.retention_until:
            retention = obs.retention_until
    legal_active = None
    for obs in present_copies:
        if obs.legal_active is not None:
            legal_active = obs.legal_active
    action = base.action_override or CATEGORY_ACTION.get(base.category, "DELETE")
    # A contact-style delete override on any present copy wins over anonymize.
    for obs in present_copies:
        if obs.action_override == "DELETE":
            action = "DELETE"
    evidence = _cite(
        admissible,
        audit_at,
        want_present=present,
        direct_pii=direct_pii,
        enabled=enabled,
        restore_allowed=restore_allowed,
        action=action,
    )
    return Resolved(
        resource_id=resource_id,
        system_id=base.system_id,
        category=base.category,
        action=action,
        present=present,
        direct_pii=direct_pii,
        attributable=attributable,
        enabled=enabled,
        restore_allowed=restore_allowed,
        retention_until=retention,
        legal_active=legal_active,
        evidence_id=evidence,
        observed_at=max((obs.observed_at for obs in (present_copies or absent_copies)), default=base.observed_at),
    )


def _cite(
    copies: list[Observation],
    audit_at: str,
    want_present: bool,
    direct_pii: bool,
    enabled: bool | None,
    restore_allowed: bool | None,
    action: str,
) -> str:
    def supports(obs: Observation, require_citable: bool) -> bool:
        if require_citable and not _citable(obs, audit_at):
            return False
        if obs.observed_at > audit_at:
            return False
        if want_present and not obs.present:
            return False
        if not want_present and obs.present:
            return False
        return True

    matching = [obs for obs in copies if supports(obs, True)]
    if not matching:
        # The fact was recorded at a snapshot time at or before the audit,
        # inside a file packaged later. Cite that snapshot rather than drop it.
        matching = [obs for obs in copies if supports(obs, False)]
    pool = matching
    if not pool:
        return ""

    def rank(obs: Observation) -> tuple:
        match = 0
        if action in {"ANONYMIZE", "REDACT"} and want_present:
            if bool(obs.direct_pii) == bool(direct_pii):
                match += 2
        if action == "FLOW" and obs.enabled is not None and obs.enabled == enabled:
            match += 2
        if action == "BACKUP" and obs.restore_allowed is not None and obs.restore_allowed == restore_allowed:
            match += 2
        if action == "DELETE" and want_present and obs.direct_pii:
            match += 1
        return (match, obs.observed_at, evidence_number(obs.evidence_id))

    return max(pool, key=rank).evidence_id


def absent_account_evidence(
    user_tokens: set[str],
    observations: list[Observation],
    scans: list[CollectionScan],
    audit_at: str,
) -> str:
    """Latest citable account snapshot that can prove a profile is gone."""
    user_files: set[str] = set()
    for obs in observations:
        if obs.observed_at <= audit_at and obs.link_ids & user_tokens:
            user_files.add(obs.evidence_id)
    scoped: list[CollectionScan] = []
    global_scans: list[CollectionScan] = []
    for scan in scans:
        if scan.category != "USER_PROFILE":
            continue
        if scan.observed_at > audit_at or scan.manifest_at > audit_at:
            # Inner snapshot time can be earlier than the bundle package time.
            if scan.observed_at > audit_at:
                continue
        if scan.manifest_at > audit_at and scan.observed_at > audit_at:
            continue
        if scan.observed_at > audit_at:
            continue
        if scan.evidence_id in user_files:
            scoped.append(scan)
        elif scan.present_ids and scan.manifest_at <= audit_at:
            global_scans.append(scan)
    pool = scoped or global_scans
    if not pool:
        return ""
    best = max(pool, key=lambda scan: (scan.observed_at, evidence_number(scan.evidence_id)))
    if best.manifest_at > audit_at:
        return ""
    return best.evidence_id
