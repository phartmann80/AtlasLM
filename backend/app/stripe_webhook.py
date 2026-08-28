import hmac
import hashlib
import time
import logging

import httpx
from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings

logger = logging.getLogger("atlas.stripe")

router = APIRouter()

# Reject events whose timestamp is older than this, to stop replay attacks.
SIGNATURE_TOLERANCE_SECONDS = 300  # 5 minutes, matches Stripe's own default


def _verify_signature(payload: bytes, sig_header: str, secret: str) -> None:
    """
    Verify the Stripe-Signature header against the raw request body.

    Raises HTTPException(400) on any failure. Returns None on success.

    The header looks like:  t=1700000000,v1=abc123...,v0=...
    Stripe signs  "{t}.{payload}"  with HMAC-SHA256 using your signing secret.
    """
    if not secret:
        # Fail closed: if we have no secret configured, do NOT accept events.
        logger.error("STRIPE_WEBHOOK_SECRET is not set; rejecting webhook.")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    # Parse the header into a dict of its comma-separated key=value pairs.
    timestamp = None
    signatures = []
    for part in sig_header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key == "t":
            timestamp = value.strip()
        elif key == "v1":
            signatures.append(value.strip())

    if timestamp is None or not signatures:
        raise HTTPException(status_code=400, detail="Malformed Stripe-Signature header")

    # Replay protection: reject events that are too old.
    try:
        event_time = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid timestamp in signature")

    if abs(time.time() - event_time) > SIGNATURE_TOLERANCE_SECONDS:
        raise HTTPException(status_code=400, detail="Timestamp outside tolerance window")

    # Recompute the expected signature over "{timestamp}.{raw_body}".
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time compare against every v1 signature Stripe sent.
    # (Stripe may send more than one during secret rotation.)
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise HTTPException(status_code=400, detail="Signature verification failed")


async def _patch_profile(params: dict, body: dict) -> None:
    """Write a tier change into the Supabase profiles table via the REST API."""
    url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(url, params=params, json=body, headers=headers)
        if resp.status_code >= 300:
            logger.error("Supabase profile update failed: %s %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="Failed to update profile")


def _resolve_tier(status: str, metadata: dict) -> str:
    """Map a Stripe subscription status + metadata to an AtlasLM tier."""
    active_states = {"active", "trialing", "past_due"}
    if status in active_states:
        # Honor the tier set on the price/subscription metadata; default to Pro.
        return metadata.get("tier", "Pro")
    # canceled, unpaid, incomplete_expired, paused, etc. -> downgrade.
    return "Free"


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    # 1. Read the RAW body. Do NOT use request.json() first. Signature
    #    verification must run against the exact bytes Stripe signed.
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    # 2. Verify before doing anything else.
    _verify_signature(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)

    # 3. Only now is it safe to parse and act on the event.
    import json
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        user_id = obj.get("client_reference_id")
        customer = obj.get("customer")
        tier = obj.get("metadata", {}).get("tier", "Pro")
        if user_id:
            await _patch_profile(
                params={"id": f"eq.{user_id}"},
                body={"tier": tier, "stripe_customer_id": customer},
            )

    elif event_type == "customer.subscription.updated":
        customer = obj.get("customer")
        tier = _resolve_tier(obj.get("status", ""), obj.get("metadata", {}))
        if customer:
            await _patch_profile(
                params={"stripe_customer_id": f"eq.{customer}"},
                body={"tier": tier},
            )

    elif event_type == "customer.subscription.deleted":
        customer = obj.get("customer")
        if customer:
            await _patch_profile(
                params={"stripe_customer_id": f"eq.{customer}"},
                body={"tier": "Free"},
            )

    else:
        # Acknowledge unhandled events so Stripe stops retrying them.
        logger.info("Unhandled Stripe event type: %s", event_type)

    return {"status": "success"}
