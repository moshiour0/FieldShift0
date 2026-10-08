"""Actionable provider errors with credentials and account identifiers removed."""
from __future__ import annotations

import os
import re


def safe_error(exc: Exception) -> str:
    message = str(exc)
    for key, value in os.environ.items():
        if value and key.startswith("FIELD_SHIFT_") and any(part in key for part in ("TOKEN", "PASSWORD", "USER", "JSON", "PROJECT")):
            message = message.replace(value, "[redacted]")
    message = re.sub(r"-----BEGIN.*?-----END[^-]+-----", "[redacted key]", message, flags=re.DOTALL)
    message = re.sub(r"(?i)(bearer|basic)\s+\S+", r"\1 [redacted]", message)
    message = re.sub(r"[\w.+-]+@[\w.-]+", "[redacted account]", message)
    message = re.sub(r"projects/[\w.-]+", "projects/[redacted]", message)
    message = re.sub(r"https?://\S+", "[provider URL]", message)
    return f"{type(exc).__name__}: {' '.join(message.split())[:450]}"
