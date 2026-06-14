"""
Document parsing for the Case-File Analyzer.

Supports PDF (pypdf, with pdfplumber fallback), and plain text (.txt/.md).
OCR (pytesseract) is OPTIONAL and import-guarded — if Tesseract / pytesseract
is not installed, OCR is silently skipped with a note rather than crashing.

GUARDRAIL: Operates ONLY on bytes the user uploads. No web scraping, no
external fetching, no PII harvesting.
"""
from __future__ import annotations

import io
from typing import Tuple


def _parse_pdf(data: bytes) -> str:
    text = ""
    # Primary: pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        text = ""

    # Fallback: pdfplumber (often better on tricky layouts)
    if not text:
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
        except Exception:
            text = ""

    # Optional OCR — only if no embedded text AND tesseract is available.
    if not text:
        ocr_text = _try_ocr_pdf(data)
        if ocr_text:
            text = ocr_text
    return text


def _try_ocr_pdf(data: bytes) -> str:
    """Import-guarded OCR. Returns '' if any OCR dependency is missing."""
    try:
        import pytesseract  # noqa: F401
        from pdf2image import convert_from_bytes  # noqa: F401
    except Exception:
        return ""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(data)
        return "\n".join(pytesseract.image_to_string(img) for img in images).strip()
    except Exception:
        # Tesseract binary missing or any OCR error — skip OCR gracefully.
        return ""


def parse_document(filename: str, data: bytes) -> Tuple[str, str]:
    """
    Parse uploaded bytes into text.

    Returns (text, note). `note` carries any non-fatal info (e.g. OCR skipped).
    """
    name = (filename or "").lower()
    note = ""

    if name.endswith(".pdf"):
        text = _parse_pdf(data)
        if not text:
            note = (
                "No extractable text found. If this is a scanned PDF, install "
                "Tesseract OCR (and pytesseract + pdf2image) to enable OCR."
            )
        return text, note

    if name.endswith((".txt", ".md", ".markdown", ".text")):
        for enc in ("utf-8", "latin-1"):
            try:
                return data.decode(enc).strip(), note
            except Exception:
                continue
        return data.decode("utf-8", errors="ignore").strip(), note

    # Unknown extension: best-effort decode as text.
    try:
        return data.decode("utf-8", errors="ignore").strip(), "Unknown file type; decoded as plain text."
    except Exception:
        return "", "Could not parse this file type."
