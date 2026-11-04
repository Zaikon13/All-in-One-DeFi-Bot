"""Telegram message formatting helpers (2026-11-04). Pure; unit-tested offline.

The bot sends with parse_mode="Markdown" (Telegram's LEGACY Markdown). In that
mode bold is *single* asterisks. The codebase (and its AI prompts) write
**double**, which legacy Markdown parses as an EMPTY bold span: the asterisks
vanish and nothing is ever bold. Rather than touch every renderer, the send
layer converts `**` -> `*` right before sending.

Telegram also rejects messages over 4096 characters (400), so long reports are
split on line boundaries; and an unbalanced `_`/`*`/`` ` `` makes the whole
message fail ("can't parse entities"), so senders retry as plain text using
`plain_text` (markers stripped, escapes undone).
"""
import re

TG_MAX_CHARS = 4096
SAFE_CHUNK = 4000


def to_tg_markdown(text: str) -> str:
    """`**bold**` (CommonMark) -> `*bold*` (Telegram legacy Markdown)."""
    return str(text or "").replace("**", "*")


def plain_text(text: str) -> str:
    """Fallback body for a message Telegram refused to parse: drop the bold /
    code markers and undo backslash escapes so nothing renders as noise."""
    s = to_tg_markdown(text)
    s = s.replace("\\_", "_").replace("\\*", "*").replace("\\`", "`").replace("\\[", "[")
    return s.replace("*", "").replace("`", "")


def split_message(text: str, limit: int = SAFE_CHUNK) -> list:
    """Split into chunks <= limit, preferring line boundaries (entities in this
    codebase never span lines, so a line split never cuts a Markdown pair)."""
    s = str(text or "")
    if len(s) <= limit:
        return [s]
    chunks, cur = [], ""
    for line in s.split("\n"):
        while len(line) > limit:  # a single monster line: hard-cut it
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()] or [s[:limit]]


_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")


def legacy_markdown_balanced(text: str) -> bool:
    """True if Telegram legacy Markdown would parse `text` without the
    "can't find end of entity" error: after removing escaped characters and
    [label](url) links, `*`, `_` and backticks each appear an even number of
    times. A conservative check used by tests on the bot's static messages."""
    s = to_tg_markdown(text)
    s = re.sub(r"\\[_*`\[]", "", s)
    s = _LINK_RE.sub("", s)
    return all(s.count(ch) % 2 == 0 for ch in ("*", "_", "`"))
