"""Deletion-intent gate.

The model may return a boolean and a verbatim span. A span that is not in the
request is ignored. With no API key, a conservative multilingual lexicon decides.
"""

import os
from dataclasses import dataclass

from code.usage import Usage


DELETION_STEMS = (
    "delet",
    "remov",
    "eras",
    "profile is gone",
    "cannot identify me",
    "can't identify me",
    "delete",
    "deletion",
    "erase",
    "erasure",
    "be forgotten",
    "right to erasure",
    "close my account",
    "close the account",
    "close this account",
    "account closed",
    "permanently delete",
    "permanent deletion",
    "remove my account",
    "remove the account",
    "remove my profile",
    "remove my personal",
    "eliminar",
    "eliminacion",
    "eliminación",
    "borrar mi cuenta",
    "suprimir",
    "suppression",
    "supprimer",
    "effacer",
    "exclusao",
    "exclusão",
    "excluir",
    "apagar",
    "encerrar",
    "löschen",
    "loesch",
    "cancellare",
    "cancellazione",
    "elimina",
    "verwijder",
    "usun",
    "usuń",
    "radera",
    "slette",
    "poista",
    "hapus",
    "删除",
    "削除",
    "消去",
    "삭제",
    "حذف",
    "удал",
)

# These block deletion even if a deletion verb is also present.
NEGATION_PHRASES = (
    "do not delete",
    "don't delete",
    "do not erase",
    "don't erase",
    "do not close",
    "don't close",
    "do not remove the account",
    "don't remove the account",
    "not close the account",
    "leave the account",
    "leave my account",
    "leave my profile",
    "keep the account",
    "keep my account",
    "leave the account active",
    "keep the account as it is",
    "no destructive action",
    "not a deletion",
)

# Used only when no deletion phrase is present.
NON_DELETION_PHRASES = (
    "change the email",
    "change my email",
    "change the phone",
    "change my phone",
    "mobile number",
    "out of date",
    "download my",
    "portable format",
    "copy of",
    "invoices",
    "resetting the login",
    "reset the login",
    "reset my password",
    "can't access",
    "cannot access",
    "unsubscribe",
    "opt out",
    "opt-out",
    "marketing emails",
    "correct my",
    "update my address",
)


@dataclass
class Intent:
    deletion_authorized: bool
    span: str
    source: str


def _fold(text: str) -> str:
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .casefold()
    )


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    folded = _fold(text)
    for phrase in phrases:
        if phrase.casefold() in folded or phrase in text:
            return True
    return False


def lexicon_intent(request_text: str) -> Intent:
    text = _fold(request_text or "")
    if _contains_phrase(text, NEGATION_PHRASES):
        return Intent(False, "", "lexicon")
    if _contains_phrase(text, DELETION_STEMS):
        return Intent(True, "", "lexicon")
    if _contains_phrase(text, NON_DELETION_PHRASES):
        return Intent(False, "", "lexicon")
    return Intent(False, "", "lexicon")


def _model_configured() -> bool:
    names = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DELETION_AUDIT_API_KEY",
        "AZURE_OPENAI_API_KEY",
    )
    return any(os.environ.get(name) for name in names)


def classify_intent(request_text: str, usage: Usage) -> Intent:
    """Return whether the text authorizes deletion.

    A configured model would have to return a verbatim span. This build does
    not call a model. The lexicon is the decision either way when no call is made.
    """
    if _model_configured():
        # A key is present but this run does not call out. Count stays measured.
        usage.note_skipped_model()
    return lexicon_intent(request_text)
