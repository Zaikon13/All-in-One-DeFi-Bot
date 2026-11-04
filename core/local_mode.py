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
    """Print an outbound message in full (console mode replaces the Telegram send).
    Same redaction as the [tg-out] log line (apikey/api_key masked), and the chat
    id is never echoed, so console output can't leak a credential.
    NEVER raises: a non-UTF-8 stdout (Windows cp1252, a redirect) gets the text
    with unencodable characters replaced, and any other write error is ignored —
    a console print must not crash the sender (the worker's startup message)."""
    try:
        from core.log_redaction import redact
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        bar = "─" * 60
        body = redact(str(text))
        out = f"\n{bar}\n📨 [{ts} UTC] {source}\n{body}\n{bar}\n"
        try:
            sys.stdout.write(out)
        except UnicodeEncodeError:
            enc = sys.stdout.encoding or "ascii"
            sys.stdout.write(out.encode(enc, "replace").decode(enc))
        sys.stdout.flush()
    except Exception:
        pass


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


def configured_allowed_chats() -> set:
    """The chat allow-list shared by the webhook and the local poller, read from
    env at call time: TELEGRAM_ALLOWED_CHAT_IDS, else TELEGRAM_CHAT_ID. Callers
    treat an EMPTY set as fail-closed (serve nobody)."""
    return allowed_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID"))


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
