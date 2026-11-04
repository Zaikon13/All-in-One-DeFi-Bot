"""Standalone runner: bot + worker in ONE process, no Railway, no public URL.

    python run_local.py               # console mode if no TELEGRAM_BOT_TOKEN, else Telegram polling
    python run_local.py --console     # never touch Telegram; type commands, replies print here
    python run_local.py --selftest    # run every command once in console mode, then exit
    python run_local.py --no-worker   # commands only (no scanner / paper / alerts loops)

Telegram polling mode uses getUpdates, which Telegram refuses while a webhook is
set on the same token. That is deliberate protection: if the token is already
served by another bot (e.g. the one Grok runs), this runner REFUSES to start
instead of silently stealing it. Use a NEW bot token from @BotFather, or pass
--take-over-webhook to explicitly delete the existing webhook.

Simulation/monitoring only — no keys, no signing, no trades (see CLAUDE.md).
"""
import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("run_local")

# Settings polling mode cannot run without: the worker's webhook guard would
# re-set a webhook (-> getUpdates 409 -> dead poller), and a remote mirror URL
# would push /paper state to another service instead of this process.
_FORCED_LOCAL = (("WEBHOOK_GUARD_ENABLED", "false"), ("PAPER_MIRROR_URL", "inprocess"))


def _apply_local_defaults(environ=os.environ):
    """Local-mode env, applied at import: it MUST happen before app.main / worker
    are imported (they read env at import time).
    - WEBHOOK_AUTOSET_ENABLED defaults to false (an explicit value still wins);
    - WEBHOOK_GUARD_ENABLED=false and PAPER_MIRROR_URL=inprocess are FORCED
      (warned when an explicit different value is overridden);
    - WORKER_DATA_DIR=<repo>/data ONLY when no volume is configured, so a mounted
      Railway volume (RAILWAY_VOLUME_MOUNT_PATH) keeps its state and evidence."""
    environ.setdefault("WEBHOOK_AUTOSET_ENABLED", "false")  # polling, never claim a webhook
    for key, value in _FORCED_LOCAL:
        old = environ.get(key)
        if old is not None and old != value:
            # the old value is not logged (a URL could carry credentials)
            logger.warning("run_local: forcing %s=%s (an explicit different value was set; "
                           "polling mode requires it)", key, value)
        environ[key] = value
    if not (environ.get("WORKER_DATA_DIR") or environ.get("RAILWAY_VOLUME_MOUNT_PATH")):
        environ["WORKER_DATA_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


_apply_local_defaults()

SELFTEST_COMMANDS = ["/start", "/wallet", "/signals", "/paper", "/daily_pnl", "/analyze", "/nonsense"]


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run All-in-One-DeFi-Bot locally (bot + worker).")
    p.add_argument("--console", action="store_true", help="print replies here; never call Telegram")
    p.add_argument("--selftest", action="store_true", help="run every command once (console) and exit")
    p.add_argument("--no-worker", action="store_true", help="do not start the worker loops")
    p.add_argument("--take-over-webhook", action="store_true",
                   help="delete an existing webhook on this token so polling can start")
    return p.parse_args(argv)


class _Tasks:
    """run_task() for handle_command: fire-and-forget asyncio tasks, kept referenced."""

    def __init__(self):
        self.pending = set()

    def __call__(self, fn, *args):
        t = asyncio.create_task(self._safe(fn, *args))
        self.pending.add(t)
        t.add_done_callback(self.pending.discard)

    @staticmethod
    async def _safe(fn, *args):
        try:
            await fn(*args)
        except Exception:
            logger.exception(f"command task {getattr(fn, '__name__', fn)} failed")

    async def drain(self, timeout=120):
        if self.pending:
            await asyncio.wait(set(self.pending), timeout=timeout)


async def _console_loop(handle_command, tasks, chat_id):
    print("\n💬 Console mode — type a command (/start, /wallet, /signals, /paper, "
          "/daily_pnl, /analyze). Ctrl+C or 'quit' to exit.\n", flush=True)
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:  # EOF
            await tasks.drain()
            return
        line = line.strip()
        if line in ("quit", "exit"):
            await tasks.drain(timeout=5)
            return
        if line:
            await handle_command(line if line.startswith("/") else "/" + line, chat_id, tasks)


async def _selftest(handle_command, tasks, chat_id):
    for cmd in SELFTEST_COMMANDS:
        print(f"\n>>> {cmd}", flush=True)
        await handle_command(cmd, chat_id, tasks)
        await tasks.drain(timeout=90)
    print("\n✅ selftest finished — every command produced a reply above.", flush=True)


async def _reply_setup_hint(client, base, chat_id):
    try:
        await client.post(f"{base}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"This bot is not configured yet. Set TELEGRAM_CHAT_ID={chat_id} "
                    "(only that chat will be served) and restart run_local.py."})
    except Exception as e:
        logger.warning(f"setup hint send failed: {e}")


async def _telegram_poll_loop(handle_command, tasks, token, take_over):
    import httpx
    from core.local_mode import configured_allowed_chats, extract_updates, is_chat_allowed
    from core.log_redaction import log_safe

    allowed = configured_allowed_chats()
    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=70) as client:
        info = (await client.get(f"{base}/getWebhookInfo")).json()
        hook = ((info or {}).get("result") or {}).get("url") or ""
        if hook:
            if not take_over:
                logger.error(
                    "This bot token already has a webhook (%s) — another service is serving it "
                    "(e.g. the Grok bot). Refusing to steal it. Create a NEW bot with @BotFather and "
                    "put its token in TELEGRAM_BOT_TOKEN, or rerun with --take-over-webhook.", hook)
                return
            r = (await client.post(f"{base}/deleteWebhook")).json()
            bi = (await client.get(f"{base}/getWebhookInfo")).json()
            # confirmed ONLY by an ok read-back with an empty url (a 429/error body
            # has no result -> not confirmed, never "deleted")
            res = bi.get("result") if isinstance(bi, dict) and bi.get("ok") else None
            if not r.get("ok") or not isinstance(res, dict) or res.get("url"):
                logger.error("deleteWebhook not confirmed by read-back; not polling")
                return
            logger.warning("webhook %s deleted (read-back confirmed) — polling takes over", hook)
        me = (await client.get(f"{base}/getMe")).json().get("result") or {}
        logger.info(f"Telegram polling as @{me.get('username', '?')} — allowed chats: "
                    f"{', '.join(sorted(allowed)) or 'NONE — set TELEGRAM_CHAT_ID (unknown chats get a setup hint only)'}")
        offset, backoff = 0, 2
        while True:
            try:
                resp = await client.get(f"{base}/getUpdates",
                                        params={"offset": offset, "timeout": 50,
                                                "allowed_updates": '["message","edited_message"]'})
                if resp.status_code == 409:
                    logger.error("getUpdates 409: a webhook or another poller owns this token; stopping")
                    return
                if resp.status_code in (401, 404):
                    logger.error("getUpdates HTTP %s — bot token rejected; stopping", resp.status_code)
                    return
                if resp.status_code != 200:
                    # 429 / 5xx: back off (the except below) instead of hot-looping
                    raise RuntimeError(f"getUpdates HTTP {resp.status_code}")
                updates, offset = extract_updates(resp.json(), offset)
                for chat_id, text in updates:
                    if not allowed:
                        # fail closed: with no allow-list nobody gets wallet data;
                        # tell the sender which id to configure instead
                        logger.warning(f"no TELEGRAM_CHAT_ID set — message from chat {log_safe(chat_id)} not served")
                        await _reply_setup_hint(client, base, chat_id)
                        continue
                    if not is_chat_allowed(chat_id, allowed):
                        logger.info(f"ignoring message from non-allowed chat {log_safe(chat_id)}")
                        continue
                    await handle_command(text, chat_id, tasks)
                backoff = 2
            except Exception as e:
                logger.warning(f"poll error (retry in {backoff}s): {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)


def _seed_paper_mirror(bot):
    """Local mode can read the state file directly, so /paper works from boot
    (on Railway the bot has no volume and waits for the worker's first push)."""
    try:
        import core.paper_trading as paper
        if os.path.exists(paper.state_path()):
            bot.set_paper_mirror(paper.compact_paper_state(paper.load_state()), None, None)
    except Exception as e:
        logger.info(f"paper mirror seed skipped: {e}")


async def _amain(args) -> int:
    """Run the jobs; returns the process exit code. 0 = clean (selftest done, or
    the console loop ended on quit/EOF); 1 = a job crashed, or the worker or the
    poller stopped (both are meant to run forever) — so a supervisor such as
    Railway's ON_FAILURE restart policy sees the stop instead of a silent exit 0."""
    import app.main as bot
    import worker
    import core.paper_trading as paper

    logger.info(f"state dir: {worker.PERSISTENCE_BASE} | paper: {paper.state_path()}")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or "local"
    tasks = _Tasks()
    _seed_paper_mirror(bot)
    jobs = []
    if not args.no_worker and not args.selftest:
        jobs.append(asyncio.create_task(worker.main(), name="worker"))
    if args.selftest:
        await _selftest(bot.handle_command, tasks, chat_id)
        return 0
    from core.local_mode import console_mode
    if console_mode():  # same parse as every sender (1/true/yes)
        jobs.append(asyncio.create_task(_console_loop(bot.handle_command, tasks, chat_id), name="console"))
    else:
        jobs.append(asyncio.create_task(
            _telegram_poll_loop(bot.handle_command, tasks, bot.BOT_TOKEN, args.take_over_webhook),
            name="poller"))
    done, _ = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
    rc = 0
    for j in done:
        name = j.get_name()
        exc = None if j.cancelled() else j.exception()
        if exc is not None:
            logger.error("%s crashed — exiting 1", name, exc_info=exc)
            rc = 1
        elif name in ("worker", "poller"):
            logger.error("%s stopped (it should run forever) — exiting 1", name)
            rc = 1
        # a console job that returns = the user quit (rc stays 0)
    for j in jobs:
        j.cancel()
    await asyncio.gather(*jobs, return_exceptions=True)
    return rc


def main(argv=None):
    args = _parse_args(argv)
    if args.console or args.selftest or not os.getenv("TELEGRAM_BOT_TOKEN"):
        os.environ["CONSOLE_MODE"] = "true"
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        rc = asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print("\nbye", flush=True)
        return
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()
