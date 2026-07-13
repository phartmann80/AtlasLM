"""Short-lived signed context used only by the private Mastra boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from .config import settings


def _encoded(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign_internal_context(payload: dict[str, Any]) -> tuple[str, str]:
    """Return an opaque context header and its HMAC signature."""
    token = _encoded(payload)
    signature = hmac.new(
        settings.ATLAS_INTERNAL_SIGNING_SECRET.encode("utf-8"),
        token.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return token, signature


def verify_internal_context(token: str, signature: str) -> dict[str, Any]:
    if not settings.ATLAS_INTERNAL_SIGNING_SECRET:
        raise ValueError("Internal signing secret is not configured")
    expected = hmac.new(
        settings.ATLAS_INTERNAL_SIGNING_SECRET.encode("utf-8"),
        token.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid internal signature")
    padded = token + ("=" * (-len(token) % 4))
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise ValueError("Expired internal context")
    if not payload.get("userId") or not payload.get("workspaceId"):
        raise ValueError("Incomplete internal context")
    return payload
