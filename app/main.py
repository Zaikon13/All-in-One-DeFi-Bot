from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import logging
import httpx
from datetime import datetime
import asyncio
import json

# Reuse Grok client + wallet helpers from core/ (SOT for calls, prompts, quality gates - consolidated 2026-06-04)
# (Review Agent 2026-06-04: switch for timeout/quality support; balances/tx for live grok-analyze)
from core.claude_client import call_grok, load_prompt, is_valid_grok_response
from core.wallet import get_wallet_balances, get_recent_transactions
from core.log_redaction import install_log_redaction, tg_out_log
from core.telegram_webhook import resolve_webhook_url, ensure_webhook

# Config
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_URL') or os.getenv('APP_URL') or "https://web-gpl6-production.up.railway.app"
RAILWAY_SERVICE_NAME = os.getenv('RAILWAY_SERVICE_NAME', 'unknown')

install_log_redaction()  # Part D: strip apikey= from logs (log-only)

app = FastAPI(title="All-in-One-DeFi-Bot")

# Webhook self-heal, part (a) (2026-07-18): the bot claims its own webhook on
# every startup, so a deploy/restart can never leave commands pointed at a dead
# service. Target precedence: WEBHOOK_URL > APP_URL > RAILWAY_PUBLIC_DOMAIN
# (auto-set by Railway on web services) > canonical bot domain. Env-gated;
# defensive; read-back confirmed (a write isn't DONE until read back).
WEBHOOK_AUTOSET_ENABLED = os.getenv("WEBHOOK_AUTOSET_ENABLED", "true").lower() == "true"


@app.on_event("startup")
async def _autoset_webhook():
    if not (WEBHOOK_AUTOSET_ENABLED and BOT_TOKEN):
        logging.info("[webhook] startup autoset disabled or no token; skipping")
        return
    target = resolve_webhook_url(os.getenv("WEBHOOK_URL"), os.getenv("APP_URL"),
                                 os.getenv("RAILWAY_PUBLIC_DOMAIN"))
    try:
        async with httpx.AsyncClient() as client:
            outcome = await ensure_webhook(client, BOT_TOKEN, target)
        logging.info(f"[webhook] startup autoset outcome: {outcome}"
                     + (" (restored + confirmed by read-back)" if outcome == "restored" else ""))
    except Exception as e:
        logging.error(f"[webhook] startup autoset error (non-fatal): {e}")

# --- Paper-state mirror (2026-07-17, simulation only) ---------------------------
# The /data volume attaches only to the worker, so the bot cannot read
# paper_state.json. The worker POSTs a compact mirror here after every engine
# step; /paper renders from it. Auth: sha256 of the shared TELEGRAM_BOT_TOKEN
# (the token itself never travels). In-memory only — after a bot restart the
# mirror refills on the worker's next cycle (~5 min).
_paper_mirror: dict | None = None


def _paper_mirror_auth() -> str:
    import hashlib
    return hashlib.sha256((BOT_TOKEN or "").encode()).hexdigest()[:32]


def get_paper_mirror() -> dict | None:
    return _paper_mirror


def get_signals_mirror() -> dict | None:
    return (_paper_mirror or {}).get("signals") if _paper_mirror else None


async def send_telegram_message(text: str, chat_id: str = None, reply_markup=None):
    tg_out_log(logging.getLogger("app.main"), text)
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = {
                "chat_id": cid,
                "text": text,
                "parse_mode": "Markdown"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload)
    except Exception as e:
        logging.error(f"Send message error: {e}")


async def get_all_balances(chat_id: str):
    """Delegate to the canonical balances command to avoid duplicate balance logic."""
    from app.commands import get_all_balances as cmd_get_all_balances
    return await cmd_get_all_balances(chat_id)


async def process_daily_pnl(chat_id: str):
    """Production webhook handler for /daily_pnl (and /dailypnl).
    Now delegates to core.pnl_calculator.get_daily_pnl_report() for:
    - Async-safe Covalent data (no event loop block)
    - Grok AI insights with hard timeout + reliable fallback
    Broken inline Explorer + PnLCalculator import removed (was non-functional).
    """
    if not WALLET_ADDRESS:
        await send_telegram_message("WALLET_ADDRESS not configured", chat_id)
        return
    await send_telegram_message("🔄 Generating daily PnL report...", chat_id)
    try:
        # Core async path (Grok-enhanced with safe fallback). Reuses core/ logic.
        from core.pnl_calculator import get_daily_pnl_report
        report = await get_daily_pnl_report()
        await send_telegram_message(report, chat_id)
    except Exception as e:
        logging.exception("daily_pnl error")
        await send_telegram_message("Error generating daily PnL report. Please try again.", chat_id)


# --- Live Grok Analyze support (Review Agent 2026-06-04 binding requirements) ---
# Reuses core/ for balances + new tx helper. Python compacts data before prompt.
# Quality gate + 25s timeout + safe fallback modeled on get_daily_pnl_report.
# Command path uses background_tasks (like balances/daily_pnl); HTTP direct.
async def _get_grok_live_context(wallet_address: str) -> dict:
    """Build compact live summaries for the Grok prompt (balances + recent txs).
    Defensive: returns safe defaults on any fetch error. No impact on /balances or /wallet.
    """
    if not wallet_address:
        return {"preview": "unknown", "balances": "N/A", "txs": "N/A"}
    try:
        balances = await get_wallet_balances(wallet_address)
        recent = await get_recent_transactions(wallet_address, 20)  # limit=20 per Review Agent 2026-06-04 helper spec
        preview = f"{wallet_address[:6]}...{wallet_address[-4:]}"
        b_lines = [f"CRO: {balances.get('cro', 0):,.4f}"]
        for sym, amt in sorted((balances.get("tokens") or {}).items(), key=lambda x: -x[1])[:5]:
            if amt > 0.0001:
                b_lines.append(f"• {sym}: {amt:,.4f}")
        bsum = "\n".join(b_lines)
        tsum = "\n".join(f"• {t}" for t in recent) if recent else "No recent transactions found."
        return {"preview": preview, "balances": bsum, "txs": tsum}
    except Exception as e:
        logging.exception("grok live context fetch error")
        return {"preview": "error", "balances": "fetch error", "txs": "fetch error"}


async def process_grok_analyze(chat_id: str):
    """Background worker for /grok-analyze (Telegram).
    Fetches live data via core/, builds prompt, calls Grok with timeout + gate + fallback.
    (Thinking message sent *immediately* in webhook handler before background_tasks.add_task per Review Agent 2026-06-04.)
    """
    if not WALLET_ADDRESS:
        await send_telegram_message("WALLET_ADDRESS not configured", chat_id)
        return
    try:
        ctx = await _get_grok_live_context(WALLET_ADDRESS)
        prompt = load_prompt(
            "claude_wallet_analysis.txt",
            wallet_preview=ctx["preview"],
            balances_summary=ctx["balances"],
            recent_txs_summary=ctx["txs"],
        )
        # Hard timeout (25s) + quality gate + safe fallback (exact pattern from pnl_calculator.py:558-578)
        # (Review Agent 2026-06-04)
        insight = await call_grok(prompt, timeout=25.0)
        if is_valid_grok_response(insight):
            await send_telegram_message(insight.strip(), chat_id)
        else:
            logging.info("Grok live analyze low-quality or failed; using fallback")
            await send_telegram_message(
                f"Live data fetched for {ctx['preview']}.\n\n"
                f"**Balances:**\n{ctx['balances']}\n\n"
                f"**Recent activity:**\n{ctx['txs']}\n\n"
                "(Grok insight temporarily unavailable - raw context shown above)",
                chat_id,
            )
    except Exception as e:
        logging.exception("grok analyze error")
        await send_telegram_message("Error generating live Grok analysis. Please try again.", chat_id)


@app.get("/")
@app.get("/health")
async def health():
    return {"ok": True, "service": RAILWAY_SERVICE_NAME, "status": "running"}


@app.post("/internal/paper-state")
async def paper_state_mirror(req: Request):
    """Worker-only push of the paper-trading state mirror (simulation data, no
    secrets). Rejects without the shared-secret hash; caps payload size."""
    global _paper_mirror
    import hmac
    if not BOT_TOKEN:  # empty token -> auth would be a public constant; refuse
        return JSONResponse({"ok": False}, status_code=403)
    if not hmac.compare_digest(req.headers.get("X-Paper-Auth") or "", _paper_mirror_auth()):
        return JSONResponse({"ok": False}, status_code=403)
    body = await req.body()
    if len(body) > 200_000:
        return JSONResponse({"ok": False, "error": "too large"}, status_code=413)
    try:
        payload = json.loads(body)
        if isinstance(payload, dict) and isinstance(payload.get("state"), dict):
            _paper_mirror = {"state": payload["state"],
                             "signals": payload.get("signals") if isinstance(payload.get("signals"), dict) else None,
                             "as_of": payload.get("as_of")}
            return {"ok": True}
    except Exception:
        pass
    return JSONResponse({"ok": False}, status_code=400)


@app.post("/grok/analyze")
async def grok_analyze(req: Request):
    """Claude-powered wallet analysis (live data); route kept at /grok/analyze for compatibility.
    Updated for live balances + recent txs (Review Agent 2026-06-04).
    Uses core.claude_client (via the call_grok alias) with timeout + quality gate. Supports custom wallet in payload.
    """
    try:
        data = await req.json()
        wallet = data.get("wallet", WALLET_ADDRESS)
        ctx = await _get_grok_live_context(wallet)
        prompt = load_prompt(
            "claude_wallet_analysis.txt",
            wallet_preview=ctx["preview"],
            balances_summary=ctx["balances"],
            recent_txs_summary=ctx["txs"],
        )
        insight = await call_grok(prompt, timeout=25.0)
        if is_valid_grok_response(insight):
            return {"ok": True, "analysis": insight.strip(), "live_context_used": True}
        else:
            # safe fallback: return raw context + note (never worse than before)
            # (Review Agent 2026-06-04)
            return {
                "ok": True,
                "analysis": (
                    f"Live data for {ctx['preview']}.\n\n"
                    f"**Balances:**\n{ctx['balances']}\n\n"
                    f"**Recent activity:**\n{ctx['txs']}\n\n"
                    "(Grok insight unavailable this time - raw context shown)"
                ),
                "live_context_used": True,
            }
    except Exception as e:
        logging.exception("grok/analyze http error")
        return {"ok": False, "error": str(e)}


@app.post("/telegram/webhook")
async def telegram_webhook(req: Request, background_tasks: BackgroundTasks):
    try:
        payload = await req.json()
        message = payload.get("message") or payload.get("edited_message") or {}
        text = (message.get("text") or "").strip().lower()
        chat_id = str((message.get("chat") or {}).get("id", ""))
    except:
        return JSONResponse({"ok": False}, status_code=400)

    if text.startswith("/start"):
        menu = """**👋 Welcome to All-in-One DeFi Bot!**

**Available Commands:**

• /daily_pnl — Advanced daily PnL report
• /balances — Full wallet balances with USD
• /wallet — Same as /balances
• /bal — Quick balance check
• /grok-analyze — AI-powered analysis
• /paper — 🧪 simulated trading status
• /signals — 🔎 live multi-chain discovery feed"""
        reply_markup = {
            "keyboard": ["/daily_pnl", "/balances", "/grok-analyze"],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }
        await send_telegram_message(menu, chat_id, reply_markup=reply_markup)

    elif text in ("/balances", "/wallet", "/bal", "/balance"):
        background_tasks.add_task(get_all_balances, chat_id)

    elif text == "/paper":
        from app.commands import get_paper_status
        background_tasks.add_task(get_paper_status, chat_id)

    elif text == "/signals":
        from app.commands import get_signals
        background_tasks.add_task(get_signals, chat_id)

    elif text in ("/daily_pnl", "/dailypnl"):
        background_tasks.add_task(process_daily_pnl, chat_id)

    elif text == "/grok-analyze":
        # Per Review Agent 2026-06-04: immediate thinking msg + background dispatch (matches balances/daily_pnl pattern)
        await send_telegram_message("🔄 Generating live Grok analysis...", chat_id)
        background_tasks.add_task(process_grok_analyze, chat_id)

    else:
        await send_telegram_message("Unknown command. Type /start for the menu.", chat_id)

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
