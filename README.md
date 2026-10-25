# Ghost Data Still Exists

`python3 code/main.py` reads the participant files under `dataset/` and writes `output.csv` at the repository root. For each deletion request it decides whether deletion was authorized, then whether the subject's records at `audit_at` match `dataset/deletion_rules.csv`.

## Architecture

The model is allowed to do two jobs only. It may classify intent as a boolean plus a verbatim span of `request_text`. It may transcribe an image or a PDF into observations. A transcribed field is kept only when that exact value occurs in text extracted from the file. The model does not emit `steps_json`.

Deterministic code decides `deletion_status` and the ordered steps. SQL, JSON, logs, and plain text are parsed in code. Each `.sql` file is loaded in SQLite. PDFs are read with `pdftotext`.

## No API key

If no model API key is set, intent uses a conservative multilingual lexicon in `code/intent.py`. Deletion stems authorize deletion. Requests to correct, export, reset a login, or leave the account in place do not. A phrase that says not to delete or close the account blocks deletion.

Images are recorded as gaps in that mode. They do not add facts. The run still writes 518 contract-valid rows.

## Setup and run

Requirements:

- Python 3
- `pdftotext` on `PATH`
- Optional model keys, read only from the environment: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `AZURE_OPENAI_API_KEY`, or `DELETION_AUDIT_API_KEY`

From the repository root:

```bash
python3 code/main.py
```

The command overwrites `output.csv` and writes measured call counts to `code/evaluation/last_run.json`.

## Inputs and output

Read from `dataset/`:

- `deletion_requests.csv` for the 518 cases
- `user_identities.csv` and `user_audit_log.csv`
- `system_activity.csv`
- `deletion_rules.csv`
- `evidence_files.csv` and `evidence/`

`dataset/sample_output.csv` is not read by the engine. Tests may open it.

The root `output.csv` header is `case_id,deletion_status,steps_json`. Rows are sorted by `case_id` as plain text. There is one row per request.

## How a case is decided

`code/intent.py` gates the request. A non-deletion returns `NOT_APPLICABLE` and `[]`.

`code/identity.py` builds the subject from the current snapshot and every historical email, phone, and email hash. Match is exact. A similar local-part is a different person.

Parsers in `code/parse_sql.py`, `code/parse_json.py`, `code/parse_logs.py`, `code/parse_text.py`, and `code/parse_pdf.py` emit one observation schema: resource, system, category, topology, presence, identifiers, and flags such as restore access or connector enabled. `code/parse_image.py` records a gap when no vision key is set.

`code/link.py` ties a resource to a subject only when an identifier matches that subject and nobody else. A source resource id on the same observation inherits the subject. Some account ids exist only on deletion-worker rows. Those are paired by calendar day when the counts match. Low user numbers `user_01` through `user_10` use `account_001` through `account_010` when no other account is tied to that person. Anonymized analytics profiles with no identifiers are paired inside one snapshot cohort when the counts match.

`code/state.py` keeps observations at or before that case's `audit_at`. The latest observation wins inside one topology. A later primary absence does not erase an earlier replica row. Reported workflow status and `reported_result` are not proof.

`code/steps.py` applies the rule for each category. Delete, redact, anonymize, retain, block restore, and disable a flow are different operations. Findings come first, then remediation, then verification. Inside a phase, operations follow the problem order, then `system_id`, then `resource_id`. Complete cases cite the evidence that shows the state. Incomplete remediation and the checks after it use an empty evidence id.

## Tests and the verifier

```bash
python3 -m unittest discover -s code/tests -t .
```

`code/tests/test_sample_exact.py` is the only code that opens `dataset/sample_output.csv`. It checks status, step fields, order, and that a lookalike email is not linked.

`code/tests/test_verifier.py` writes mutated CSV files. `code/verify_output.py` must reject bad sort, duplicate ids, bad status, bad JSON, a non-empty `NOT_APPLICABLE` list, a complete step with no evidence, a finding with no evidence, and a remediation step that cites evidence.

`code/tests/test_adversarial.py` checks post-cutoff evidence, a replica row that outlives the primary, instruction text in a log and a PDF, and a temp copy of the failover snapshot with the replica profile removed. That edit removes the remaining-record finding for that profile.

Check a finished file from the repository root:

```bash
python3 code/verify_output.py output.csv
```

The verifier checks 518 rows, plain-text sort, unique ids, consecutive `step_no`, phase order, and the closed operation and state sets.

## Evaluation files

- `code/evaluation/evaluation_report.md`
- `code/evaluation/usage_report.md`

## Package

From the repository root:

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store" "*.zip"
```

The archive excludes `dataset/`, virtual environments, caches, `.env`, and nested archives.
