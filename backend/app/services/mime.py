"""Magic-byte MIME sniffing.

We don't trust the client-supplied `Content-Type` on uploads — an attacker can
rename `payload.exe` to `invoice.png` and the browser will set it to `image/png`
on the multipart part. We sniff the first few bytes and reject when the real
format doesn't match a format we support.
"""

from __future__ import annotations

# Minimum bytes we need to decide for each format.
_MIN_BYTES = 12


class UnsupportedUpload(ValueError):
    """Raised when the upload's actual bytes don't match any accepted format."""


def sniff_mime(data: bytes) -> str | None:
    """Return a canonical MIME string for recognized formats, else None.

    Recognized: image/jpeg, image/png, image/webp, application/pdf.
    """
    if len(data) < _MIN_BYTES:
        return None

    # JPEG: FF D8 FF
    if data[0:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if data[0:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    # WEBP: "RIFF" .... "WEBP"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    # PDF: "%PDF-"
    if data[0:5] == b"%PDF-":
        return "application/pdf"

    return None


def assert_accepted(data: bytes, declared: str | None) -> str:
    """Return the sniffed MIME if recognized; raise UnsupportedUpload otherwise.

    `declared` is informational only — we log mismatches at the call site but
    make the sniffed value authoritative.
    """
    sniffed = sniff_mime(data)
    if sniffed is None:
        raise UnsupportedUpload(
            f"Upload bytes don't match a supported format "
            f"(declared: {declared or 'unknown'}). Use JPG, PNG, WEBP or PDF."
        )
    return sniffed


__all__ = ["UnsupportedUpload", "assert_accepted", "sniff_mime"]
