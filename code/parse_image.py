"""Images. Without an OCR or vision key, the file is a gap, not a guessed fact."""

import os
from pathlib import Path

from code.schema import Gap, Observation


def parse_image_file(path: Path, evidence_id: str, manifest_at: str) -> tuple[list[Observation], Gap | None]:
    del manifest_at
    key_names = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DELETION_AUDIT_API_KEY",
    )
    if not any(os.environ.get(name) for name in key_names):
        return [], Gap(
            evidence_id=evidence_id,
            path=str(path),
            reason="no vision or OCR key; image not transcribed",
        )
    # A configured model would still have to keep a field only when the value
    # occurs in the transcription. This run does not invent image facts.
    return [], Gap(
        evidence_id=evidence_id,
        path=str(path),
        reason="image transcription is not called in this run",
    )
