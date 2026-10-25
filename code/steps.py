"""Policy decisions and ordered FINDING, REMEDIATION, VERIFICATION steps."""

from code.state import Resolved

FINDING_ORDER = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
}
REMEDIATION_ORDER = {
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
}
VERIFICATION_ORDER = {
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}
PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}


def _within_retention(resolved: Resolved, audit_at: str) -> bool:
    if not resolved.retention_until:
        return True
    return resolved.retention_until >= audit_at


def include_resource(resolved: Resolved, audit_at: str) -> bool:
    action = resolved.action
    if action == "DELETE":
        return True
    if action == "REDACT":
        if resolved.category == "EMAIL_DELIVERY_LOG":
            return resolved.present and resolved.direct_pii
        return resolved.present
    if action == "ANONYMIZE":
        return resolved.present
    if action == "RETAIN":
        if not resolved.present:
            return False
        if resolved.category == "SECURITY_AUDIT_LOG":
            return _within_retention(resolved, audit_at)
        if resolved.category == "LEGAL_HOLD_RECORD":
            return resolved.legal_active is not False
        return True
    if action == "BACKUP":
        return resolved.present
    if action == "FLOW":
        return resolved.present and resolved.enabled is not None
    return resolved.present


def is_compliant(resolved: Resolved, audit_at: str) -> bool:
    action = resolved.action
    if action == "DELETE":
        return not resolved.present
    if action == "REDACT":
        return resolved.present and not resolved.direct_pii
    if action == "ANONYMIZE":
        return resolved.present and not resolved.attributable and not resolved.direct_pii
    if action == "RETAIN":
        return resolved.present and _within_retention(resolved, audit_at)
    if action == "BACKUP":
        return resolved.present and resolved.restore_allowed is False
    if action == "FLOW":
        return resolved.present and resolved.enabled is False
    return not resolved.present


def _plan(resolved: Resolved) -> tuple[tuple[str, str, str], tuple[str, str, str], tuple[str, str, str]]:
    """Return finding, remediation, verification as (op, state) or empty op."""
    action = resolved.action
    if action == "DELETE":
        return (
            ("REPORT_REMAINING_RECORD", "PRESENT"),
            ("DELETE_RECORD", "ABSENT"),
            ("VERIFY_RECORD_ABSENT", "ABSENT"),
        )
    if action == "REDACT":
        return (
            ("REPORT_EXPOSED_PII", "PRESENT"),
            ("REDACT_RECORD", "REDACTED"),
            ("VERIFY_RECORD_REDACTED", "REDACTED"),
        )
    if action == "ANONYMIZE":
        return (
            ("REPORT_EXPOSED_PII", "PRESENT"),
            ("ANONYMIZE_RECORD", "ANONYMIZED"),
            ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
        )
    if action == "RETAIN":
        return (
            ("", ""),
            ("", ""),
            ("VERIFY_RECORD_PRESENT", "PRESENT"),
        )
    if action == "BACKUP":
        return (
            ("REPORT_RESTORE_RISK", "ACTIVE"),
            ("BLOCK_RESTORE", "BLOCKED"),
            ("VERIFY_RESTORE_BLOCKED", "BLOCKED"),
        )
    if action == "FLOW":
        return (
            ("REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
            ("DISABLE_DATA_FLOW", "DISABLED"),
            ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
        )
    return (
        ("REPORT_REMAINING_RECORD", "PRESENT"),
        ("DELETE_RECORD", "ABSENT"),
        ("VERIFY_RECORD_ABSENT", "ABSENT"),
    )


def build_steps(resources: list[Resolved], audit_at: str) -> tuple[str, list[dict]]:
    included = [item for item in resources if include_resource(item, audit_at)]
    if not included:
        # An authorized deletion with no located records is not proof of completion.
        return "INCOMPLETE", []
    compliant = all(is_compliant(item, audit_at) for item in included)
    status = "COMPLETE" if compliant else "INCOMPLETE"
    drafts: list[tuple] = []
    for item in included:
        finding, remediation, verification = _plan(item)
        ok = is_compliant(item, audit_at)
        if not ok and finding[0]:
            drafts.append(("FINDING", finding[0], finding[1], item))
            drafts.append(("REMEDIATION", remediation[0], remediation[1], item))
        drafts.append(("VERIFICATION", verification[0], verification[1], item))
    drafts.sort(
        key=lambda row: (
            PHASE_ORDER[row[0]],
            _op_rank(row[0], row[1]),
            row[3].system_id,
            row[3].resource_id,
        )
    )
    steps = []
    for number, (phase, operation, state, item) in enumerate(drafts, start=1):
        if status == "COMPLETE":
            evidence_id = item.evidence_id
        elif phase == "FINDING":
            evidence_id = item.evidence_id
        else:
            evidence_id = ""
        steps.append(
            {
                "step_no": number,
                "phase": phase,
                "system_id": item.system_id,
                "resource_id": item.resource_id,
                "operation": operation,
                "state": state,
                "evidence_id": evidence_id,
            }
        )
    return status, steps


def _op_rank(phase: str, operation: str) -> int:
    if phase == "FINDING":
        return FINDING_ORDER.get(operation, 99)
    if phase == "REMEDIATION":
        return REMEDIATION_ORDER.get(operation, 99)
    return VERIFICATION_ORDER.get(operation, 99)
