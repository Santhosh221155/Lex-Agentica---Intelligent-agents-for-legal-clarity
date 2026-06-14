"""Centralized text sanitization for the ingestion pipeline.

Removes NULL bytes (\\x00) and non-printable ASCII control characters that
cause PostgreSQL (asyncpg / UTF-8) to reject inserts with:

    asyncpg.exceptions.CharacterNotInRepertoireError:
    invalid byte sequence for encoding "UTF8": 0x00

Preserves:
    - newlines (\\n), tabs (\\t), carriage returns (\\r)
    - all printable ASCII and valid Unicode characters
    - punctuation
"""

import re
import logging
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

# Pre-compiled regex: matches ASCII control chars EXCEPT \\t (0x09), \\n (0x0A), \\r (0x0D).
# Range \\x00-\\x08  : NUL, SOH, STX, ETX, EOT, ENQ, ACK, BEL, BS
# \\x0B-\\x0C        : VT, FF
# \\x0E-\\x1F        : SO through US
# \\x7F              : DEL
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize_text(text: Optional[str]) -> str:
    """Strip invalid control characters from *text*.

    Returns the sanitized string.  If *text* is ``None`` or not a ``str``,
    an empty string is returned.
    """
    if not text or not isinstance(text, str):
        return ""

    cleaned = _CONTROL_CHAR_RE.sub("", text)

    # Also strip surrogate code-points that may survive from malformed PDFs
    # (U+D800 – U+DFFF are only valid as UTF-16 pairs, not in UTF-8).
    cleaned = cleaned.translate(
        {cp: None for cp in range(0xD800, 0xDFFF + 1)}
    )

    return cleaned


def sanitize_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitize all string values in a metadata dict."""
    if not metadata or not isinstance(metadata, dict):
        return {}

    result: Dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            result[key] = sanitize_text(value)
        elif isinstance(value, dict):
            result[key] = sanitize_metadata(value)
        else:
            result[key] = value
    return result


def sanitize_and_log(
    text: str,
    *,
    document_id: Optional[int] = None,
    label: str = "page_text",
) -> str:
    """Sanitize *text* and emit an ``ingest.sanitized_text`` log entry when
    characters were actually removed.

    This is the primary entry-point used by the ingestion pipeline.
    """
    if not text or not isinstance(text, str):
        return ""

    cleaned = sanitize_text(text)
    removed = len(text) - len(cleaned)

    if removed > 0:
        LOGGER.info(
            "ingest.sanitized_text",
            extra={
                "document_id": document_id,
                "removed_character_count": removed,
                "label": label,
            },
        )
        # Also emit structured JSON log for observability dashboards
        from app.observability import log_event

        try:
            log_event(
                "ingest.sanitized_text",
                document_id=document_id,
                removed_character_count=removed,
                label=label,
            )
        except Exception:
            pass

    return cleaned
