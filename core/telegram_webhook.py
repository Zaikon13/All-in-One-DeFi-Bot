"""Telegram webhook self-heal helpers (2026-07-18, the "vaccine").

History: the webhook has repeatedly drifted to dead/duplicate services
(web-gpl6 hijacks, the 2023 chaos, the 2026-07-18 outage after the web-gpl6
deletion re-pointed it at a 404). Two defenses now exist:
  (a) the bot sets its OWN webhook on startup (app/main.py), and
  (b) the worker checks hourly and restores + alerts on drift (worker.py).
Decision logic here is pure and unit-tested offline; I/O helpers are defensive
(never raise) and never log the token or full credentialed URLs.
"""

import logging
import os

import httpx

# Canonical production webhook (the bot service's public domain).
CANONICAL_WEBHOOK_URL = "https://bot-production-3d9c.up.railway.app/telegram/webhook"
WEBHOOK_PATH = "/telegram/webhook"


def resolve_webhook_url(webhook_url=None, app_url=None, railway_domain=None,
                        default=CANONICAL_WEBHOOK_URL) -> str:
    """Pure precedence: explicit WEBHOOK_URL > APP_URL (+path) >
    RAILWAY_PUBLIC_DOMAIN (+path) > canonical default. Bases may or may not
    already carry the /telegram/webhook suffix or a trailing slash."""
    def _with_path(base: str) -> str:
        base = base.strip().rstrip("/")
        if not base:
            return ""
        if not base.startswith("http"):
            base = f"https://{base}"
        if base.endswith(WEBHOOK_PATH):
            return base
        return base + WEBHOOK_PATH

    for candidate in (webhook_url, app_url, railway_domain):
        if candidate and str(candidate).strip():
            u = _with_path(str(candidate))
            if u:
                return u
    return default


def needs_restore(info: dict, expected: str) -> bool:
    """Pure drift check on a getWebhookInfo payload (envelope or bare result).
    Empty/missing URL counts as drift (webhook must exist). A None/mangled
    payload is NOT drift — the caller skips that cycle (never act blind)."""
    if not isinstance(info, dict):
        return False
    result = info.get("result") if isinstance(info.get("result"), dict) else info
    current = (result.get("url") or "").strip()
    return current != expected


async def get_webhook_info(client: httpx.AsyncClient, token: str):
    """getWebhookInfo -> result dict, or None on any failure. Never raises."""
    if not token:
        return None
    try:
        r = await client.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=15.0)
        if r.status_code != 200:
            logging.warning(f"[webhook] getWebhookInfo HTTP {r.status_code}")
            return None
        d = r.json()
        if d.get("ok") and isinstance(d.get("result"), dict):
            return d["result"]
        logging.warning("[webhook] getWebhookInfo returned not-ok payload")
        return None
    except Exception as e:
        logging.warning(f"[webhook] getWebhookInfo failed: {type(e).__name__}")
        return None


async def set_webhook(client: httpx.AsyncClient, token: str, url: str,
                      drop_pending: bool = False) -> bool:
    """setWebhook; returns Telegram's ok&&result. Never raises."""
    if not (token and url):
        return False
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            data={"url": url, "drop_pending_updates": "true" if drop_pending else "false"},
            timeout=15.0,
        )
        d = r.json()
        ok = bool(d.get("ok")) and bool(d.get("result"))
        if not ok:
            logging.warning(f"[webhook] setWebhook rejected: {str(d.get('description'))[:80]}")
        return ok
    except Exception as e:
        logging.warning(f"[webhook] setWebhook failed: {type(e).__name__}")
        return False


async def ensure_webhook(client: httpx.AsyncClient, token: str, expected: str,
                         drop_pending: bool = False) -> str:
    """Check -> (re)set if drifted -> READ BACK to confirm (a write-action is
    not DONE until a read-back confirms it — golden rule 2026-07-18).
    Returns one of: 'ok' (already correct), 'restored' (drift fixed+confirmed),
    'failed' (set or read-back failed), 'skipped' (could not read state)."""
    info = await get_webhook_info(client, token)
    if info is None:
        return "skipped"
    if not needs_restore(info, expected):
        return "ok"
    old = (info.get("url") or "(empty)")
    logging.warning(f"[webhook] drift detected: -> {old[:60]} (expected {expected[:60]})")
    if not await set_webhook(client, token, expected, drop_pending=drop_pending):
        return "failed"
    back = await get_webhook_info(client, token)
    if back is not None and not needs_restore(back, expected):
        return "restored"
    return "failed"
