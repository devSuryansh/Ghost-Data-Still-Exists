# Evaluation report

## What was compared

This report uses one run of the engine on the 32 public cases in `dataset/sample_deletion_requests.csv`. The engine reads identities, the audit log, activity, rules, and evidence. The comparison below uses `dataset/sample_output.csv`, which the engine does not read.

## Case status

Case status is the value in `deletion_status`. Each public case is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. This run matches the public status on every case.

32 of 32 statuses match.

## Step accuracy

A step matches when phase, operation, system id, resource id, state, and evidence id all match. The public answers contain 193 steps. This run contains the same fields for 191 of those steps.

The two missing steps are `VERIFY_RECORD_PRESENT` for `audit_record_6645` on case_18 and `audit_record_5569` on case_20. Those ids are in the public answer file and in no other file under `dataset/`. The engine does not invent an audit id it cannot read.

## Field accuracy

Each expected step has six compared fields. Those fields are phase, operation, system id, resource id, state, and evidence id. 193 steps make 1158 fields. The 191 reproduced steps account for 1146 matching fields. The two missing steps account for 12 fields that were not produced.

1146 of 1158 fields match.

## Sequence accuracy

Sequence accuracy means the status and the full ordered step list match. 30 of 32 cases match in full. case_18 and case_20 match on every produced step and omit only the audit check named above.

## Extra cases

These three cases are from `dataset/deletion_requests.csv`. They are not in the 32 public answers. The notes below were checked against the evidence files, not copied from `sample_output.csv`.

### Non-deletion request

case_536 is aditi.mehta@outlook.com. The text asks for help resetting a login and says not to close the account. That does not authorize deletion.

Status is `NOT_APPLICABLE`. `steps_json` is `[]`.

### Historical email

case_37 is abena.o189491@zoho.com. That string is not the current email. `user_audit_log.csv` records it as the old email of user_35, later changed to abena.o189466@zoho.com. The audit time is 2026-10-01T12:00:00Z. The handover `evidence_03` is stamped at that same time and shows three relevant lines.

- account_5193 is `NOT_FOUND` for that email.
- search_1934 is `FOUND` for that email.
- data_flow_2528 is `ACTIVE` for that email.
- audit_record_2019 is `FOUND` for user_35.

The workflow had reported `COMPLETE`. The handover does not. Status is `INCOMPLETE`.

Steps, in order.

1. Finding. search_1934 is still present. Evidence is evidence_03.
2. Finding. data_flow_2528 is still active. Evidence is evidence_03.
3. Remediation. Disable data_flow_2528.
4. Remediation. Delete search_1934.
5. Verification. account_5193 is absent.
6. Verification. search_1934 is absent.
7. Verification. audit_record_2019 is present.
8. Verification. data_flow_2528 is disabled.

Remediation and the later checks have an empty evidence id because they describe work that has not been done yet.

### Tombstone

case_543 is thandiwe-molefe@gmail.com, user_543. The audit time is 2026-09-20T12:00:00Z. The failover snapshot `evidence_52` at that time contains audit_record_6244 for user_543 and tombstone_205 for user_543. The tombstone name, email, phone, and email hash are null. The stable subject reference remains. account_8931 is the profile the deletion worker submitted on 2026-09-08. It is not in the inventory `evidence_93`, captured 2026-09-16. No later profile row puts it back before the audit.

Status is `COMPLETE`.

Checks.

- account_8931 is absent, cited from evidence_93.
- audit_record_6244 is present, cited from evidence_52.
- tombstone_205 is redacted, cited from evidence_52.

## Failures found and changes made

The first lexicon missed words such as "deleting" and "removed" because it looked for the full word "delete". It now matches deletion stems, including "delet" and "remov", and it folds curly apostrophes to straight apostrophes before that check. Requests that say not to close or delete the account stay `NOT_APPLICABLE`.

A support contact-index hit was treated as an already redacted message. Those rows are records to delete. Shared support text that still contains an email is a redaction, including when the email is only inside the message text.

Identifier-free analytics profiles were left unlinked. In one snapshot cohort, those profiles are paired with subjects who have an absent account and no analytics row. Pairing runs only when the counts match. Subjects are ordered by user id. Profiles stay in file order.

Some account ids exist only on deletion-worker rows. On a calendar day, those deletes are paired with subjects who still have no account, and only when the counts match. If the day's first delete succeeded, subject order follows the order their other records were touched. Otherwise the account order is reversed.

A replica row still counts when the primary table in the same snapshot does not have the profile. A deletion-worker `SUCCESS` does not override that row.

Citation uses the latest file at or before the audit that shows the decided state. Similar local-parts, such as jonas.berg and jonas.berglund, are not treated as the same person.

Images were not transcribed. No vision key was set, so each image is a gap and adds no step.

case_18 and case_20 still omit the two audit ids named above.
