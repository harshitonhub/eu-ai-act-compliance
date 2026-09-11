"""Deterministic evidence-file ingestion: validate and extract text from an uploaded
file, per .claude/rules/security.md ("Validate file types, sizes, parsing behavior, and
content before processing"). No LLM involved -- pure mechanical extraction.

Parse-or-reject is the primary content-validation mechanism here (not separate
magic-byte sniffing): a mislabeled or corrupted file fails at the parsing step, not
silently produces garbage text. This does not defend against a zip-bomb-style malicious
DOCX (a .docx is a zip container); that would need custom bounded zip extraction instead
of python-docx's high-level API -- documented as a known gap in docs/security-model.md,
not addressed here, given the current scope.
"""

from __future__ import annotations

from io import BytesIO

import pypdf
from docx import Document

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}


class FileValidationError(Exception):
    """Raised when an uploaded evidence file fails validation. Callers should surface
    this to the user as feedback, not treat it as a system failure."""


def _extension_of(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _extract_txt(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileValidationError(f"Could not decode file as UTF-8 text: {exc}") from exc


def _extract_pdf(content: bytes) -> str:
    try:
        reader = pypdf.PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises assorted exception types for malformed PDFs
        raise FileValidationError(f"Could not parse PDF: {exc}") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise FileValidationError("PDF parsed but contained no extractable text.")
    return text


def _extract_docx(content: bytes) -> str:
    try:
        document = Document(BytesIO(content))
    except Exception as exc:  # python-docx raises assorted exception types for malformed files
        raise FileValidationError(f"Could not parse DOCX: {exc}") from exc
    text = "\n".join(p.text for p in document.paragraphs).strip()
    if not text:
        raise FileValidationError("DOCX parsed but contained no extractable text.")
    return text


_EXTRACTORS = {".txt": _extract_txt, ".pdf": _extract_pdf, ".docx": _extract_docx}


def extract_evidence_text(*, filename: str, content: bytes) -> str:
    if not content:
        raise FileValidationError("Uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise FileValidationError(
            f"File is {len(content)} bytes, exceeds the {MAX_FILE_SIZE_BYTES}-byte limit."
        )
    extension = _extension_of(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type {extension!r} not allowed; must be one of {sorted(ALLOWED_EXTENSIONS)}."
        )
    return _EXTRACTORS[extension](content)
