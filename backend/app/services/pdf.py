"""PDF -> PNG rasterization (first page only)."""

from __future__ import annotations

from io import BytesIO


def pdf_first_page_png(pdf_bytes: bytes, *, scale: float = 2.0) -> bytes:
    """Render page 1 of a PDF to PNG bytes. Raises ValueError on invalid input."""
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
    except ImportError as err:  # pragma: no cover - deps are pinned
        raise RuntimeError("pypdfium2 is not installed.") from err

    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as err:
        raise ValueError(f"Could not open PDF: {err}") from err

    if len(doc) == 0:
        raise ValueError("PDF has no pages.")

    page = doc[0]
    bitmap = page.render(scale=scale)
    pil = bitmap.to_pil()

    buf = BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()
