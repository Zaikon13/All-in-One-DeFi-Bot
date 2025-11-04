# app/github_webhook.py
import os
import hmac
import hashlib
import logging
from typing import Any, Dict

from fastapi import APIRouter, Header, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()
GITHUB_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")

def _verify_signature256(body: bytes, signature256: str | None) -> bool:
    """Validate X-Hub-Signature-256 using HMAC SHA256."""
    if not GITHUB_SECRET:
        # Αν δεν έχουμε secret, δεν κάνουμε reject το dev; αλλά καλύτερα να προειδοποιήσουμε.
        logging.warning("No GITHUB_APP_WEBHOOK_SECRET set; accepting without HMAC check.")
        return True
    if not signature256 or not signature256.startswith("sha256="):
        return False
    mac = hmac.new(GITHUB_SECRET.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    # constant-time compare
    return hmac.compare_digest(expected, signature256)

@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
) -> JSONResponse:
    body = await request.body()

    if not _verify_signature256(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    # Minimal handling
    if x_github_event == "ping":
        # GitHub expects 2xx to mark webhook as healthy
        return JSONResponse({"ok": True, "pong": True})

    # Add lightweight handlers if θέλεις:
    if x_github_event in {"issue_comment", "pull_request", "check_suite", "check_run", "push"}:
        logging.info("GitHub event: %s", x_github_event)
        return JSONResponse({"ok": True, "received": x_github_event})

    # Default
    return JSONResponse({"ok": True, "ignored": x_github_event})
