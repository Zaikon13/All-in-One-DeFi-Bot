"""Redact API keys from logs (2026-07-13, Part D).

The leak: httpx logs every request at INFO as "HTTP Request: GET <full-url>",
and our Explorer URLs carry ?apikey=<secret>. This module (a) silences httpx's
per-request INFO logging and (b) installs a filter on the root handlers that
rewrites any `apikey=<value>` (and `api_key=`) to `apikey=***` in EVERY log
record, whatever its source. This is a LOG-ONLY change — it never touches the
key itself, the request URLs, or any behavior.
"""
import logging
import re

# apikey / api_key value up to the next & , whitespace, quote, or end.
_SECRET_RE = re.compile(r"(?i)(api_?key=)[^&\s'\"]+")
_REDACTED = r"\1***"


def redact(text):
    """Return text with any apikey/api_key value masked. Safe on non-str."""
    if not isinstance(text, str):
        return text
    return _SECRET_RE.sub(_REDACTED, text)


class RedactingFilter(logging.Filter):
    """Mutates each record so the formatted message carries no apikey value.
    Applied at handler level so it catches records from any logger (incl. httpx)."""

    def filter(self, record):
        try:
            msg = record.getMessage()  # applies record.args
            red = redact(msg)
            if red != msg:
                record.msg = red
                record.args = ()
        except Exception:
            pass  # logging must never raise
        return True


def install_log_redaction():
    """Attach the redacting filter to the root logger's handlers and quiet httpx's
    URL-logging. Idempotent. Call once at each entrypoint (app/main.py, worker.py)."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s | %(levelname)s | %(message)s")
    filt = RedactingFilter()
    for h in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in h.filters):
            h.addFilter(filt)
    # Stop httpx/httpcore from logging full request URLs at INFO (defense in depth:
    # the filter would redact them anyway, but there's no reason to log them at all).
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
