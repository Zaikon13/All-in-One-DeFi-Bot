"""Local / standalone run mode helpers (2026-11-04).

The bot can now run as ONE process without Railway (see run_local.py):
- console mode (CONSOLE_MODE=true): every outbound Telegram message is printed to
  stdout instead of sent, so the whole bot can be exercised with no Telegram at all;
- polling mode: Telegram long-polling (getUpdates) instead of a webhook, so no
  public URL is needed.

Pure helpers only (no network) so they are unit-testable offline.
"""
import os
import sys
from datetime import datetime, timezone


def console_mode() -> bool:
    return os.getenv("CONSOLE_MODE", "false").lower() in ("1", "true", "yes")


def console_print(source: str, text: str, chat_id=None) -> None:
    """Print an outbound message in full (console mode replaces the Telegram send)."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    target = f" → chat {chat_id}" if chat_id else ""
    bar = "─" * 60
    sys.stdout.write(f"\n{bar}\n📨 [{ts} UTC] {source}{target}\n{text}\n{bar}\n")
    sys.stdout.flush()


def normalize_command(text: str) -> str:
    """'/Wallet@MyBot extra' -> '/wallet'. Non-commands -> ''. Pure."""
    t = (text or "").strip()
    if not t.startswith("/"):
        return ""
    cmd = t.split()[0].lower()
    return cmd.split("@", 1)[0]


def allowed_chat_ids(raw: str | None) -> set:
    """Comma list of chat ids allowed to talk to the bot. Empty -> no restriction."""
    return {p.strip() for p in (raw or "").split(",") if p.strip()}


def is_chat_allowed(chat_id, allowed: set) -> bool:
    return not allowed or str(chat_id) in allowed


def extract_updates(payload: dict, offset: int) -> tuple[list, int]:
    """getUpdates JSON -> ([(chat_id, text)], next_offset). Pure; tolerant of junk."""
    out = []
    nxt = offset
    if not isinstance(payload, dict) or not payload.get("ok"):
        return out, nxt
    for upd in payload.get("result") or []:
        if not isinstance(upd, dict):
            continue
        uid = upd.get("update_id")
        if isinstance(uid, int):
            nxt = max(nxt, uid + 1)
        msg = upd.get("message") or upd.get("edited_message") or {}
        text = msg.get("text")
        chat_id = (msg.get("chat") or {}).get("id")
        if text and chat_id is not None:
            out.append((str(chat_id), text))
    return out, nxt
