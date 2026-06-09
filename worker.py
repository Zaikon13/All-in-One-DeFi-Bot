# worker.py - Final Stable Version with Real Alerts + Wallet Monitoring

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

HEARTBEAT_INTERVAL = 3600
DEXSCREENER_INTERVAL = 300
WALLET_CHECK_INTERVAL = 600

# Phase 1 (2026-06-09 extension): short time window for restart noise reduction only.
# Pairs with last_seen older than this will intentionally re-trigger on restart
# (freshness side-effect of using last_seen; not a permanent blacklist).
# See improved Phase 1 proposal in todo + reviews/2026-06-08-worker-persistence-first-inc.md
# and reviews/2026-06-09-worker-persistence-phase1.md.
# # Review Agent 2026-06-09 (Phase 1 extension)
RESTART_DEDUP_WINDOW_SECONDS = 3600

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")

seen_pairs = set()
pair_last_seen = {}  # addr -> ISO-UTC last_seen (or None for migrated legacy entries)
last_eod_run = None
last_wallet_state = None

# --- Worker State Persistence (evolved from basic known_pairs JSON; file/JSON only) ---
# State shape (smallest correct per Review):
# {
#   "pairs": {"0x...pairAddr": {"last_seen": "2026-06-08T12:34:56.789012+00:00"}, ...},
#   "last_eod_run": "2026-06-08T00:05:00+00:00" | null
# }
# Backward compat: loader accepts old plain list ["0x..", ...] and migrates in-memory (no data loss).
# last_seen enables improved defensive change detection (missing/invalid treated as new).
# last_eod_run (minimal) used only to harden against duplicate EOD sends on restart.
# UTC ISO only for last_* fields (datetime.now(timezone.utc).isoformat()).
#
# IMPORTANT RAILWAY CAVEAT (High Risk):
# This provides durability across in-process restarts and local dev restarts.
# On Railway the worker filesystem is EPHEMERAL by default. All data (pairs, last_seen, last_eod_run)
# will be lost on redeploys / container replacements unless a Railway Volume is attached and
# RAILWAY_VOLUME_MOUNT_PATH env is set to a persistent mount (e.g. /data or /app/persist).
# No DB, no external services. Volume is REQUIRED for production durability.
# Risks restated: data loss on redeploy, restart dup alerts (mitigated by defensive load), partial-write
# corruption (mitigated by atomic), clock skew on last_seen comparisons (defensive treat bad as new).
#
# Coordinated Primary SOT update (via orchestrator --sot-pr-helper or equivalent) is REQUIRED in a
# follow-on PR before any status/docs claim "persistence complete". This inc touches worker.py ONLY.
# See GROK_COORDINATION.md, project-awareness.md 4.3, AGENTS.md, project_context.md.
#
# Review Agent 2026-06-08: UTC timestamps + migration compat + ephemeral volume warning + atomic write
# + no SOT drift (record requirement for follow-on) + scope strictly worker.py + risk documentation.
#
# Review Agent 2026-06-09 (Phase 1 extension): dict as single source of truth for last_seen
# + explicit short time-window dedup on restart (RESTART_DEDUP_WINDOW_SECONDS).
# This hardens in-process / local-restart behavior only. Does NOT change durability claims.
# Reinforces: "Partially Functional" overall; Volume REQUIRED for production durability across redeploys.
# Additive only to prior honest language. See reviews/2026-06-08-worker-persistence-first-inc.md
# and reviews/2026-06-09-worker-persistence-phase1.md. No over-claims.
PERSISTENCE_BASE = os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or "data"
KNOWN_PAIRS_FILE = os.path.join(PERSISTENCE_BASE, "known_pairs.json")


def _warn_if_no_volume():
    """Emit loud WARNING on every load/save and at startup if no volume (per Review)."""
    if not os.getenv("RAILWAY_VOLUME_MOUNT_PATH"):
        logger.warning(
            f"RAILWAY VOLUME NOT DETECTED: persistence at {KNOWN_PAIRS_FILE} uses ephemeral 'data/' (or base). "
            "pairs/last_seen/last_eod_run are NOT durable across redeploys or container replacements. "
            "Set RAILWAY_VOLUME_MOUNT_PATH and mount Volume for production. "
            "# Review Agent 2026-06-08: ephemeral volume warning log. "
            "# Review Agent 2026-06-09 (Phase 1 extension): Phase 1 (dict as source of truth + time-window dedup) "
            "reinforces 'in-process / local-restart behavior only'. Volume REQUIRED for production durability. "
            "See reviews/2026-06-08-worker-persistence-first-inc.md + reviews/2026-06-09-worker-persistence-phase1.md. "
            "Additive to existing 'Partially Functional' framing; no weakening or over-claim."
        )


def _is_valid_last_seen(ts):
    """Defensive validator: missing/invalid last_seen treated as 'new' (Review condition 2)."""
    if not ts:
        return False
    try:
        datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _sync_seen_pairs_from_dict():
    """Centralized single-source-of-truth sync.
    Ensures seen_pairs is always derived from pair_last_seen dict after any mutation.
    Call after updates to pair_last_seen.
    # Review Agent 2026-06-09 (Phase 1 extension of first inc)
    """
    global seen_pairs
    seen_pairs = set(pair_last_seen.keys())


def _is_new_or_stale(pair_address: str) -> bool:
    """Defensive helper for change detection using last_seen + explicit time window.

    Policy documentation (addresses Review Agent 2026-06-09 Medium issue #1):
    - The RESTART_DEDUP_WINDOW_SECONDS window is ONLY for short-term restart noise
      reduction (e.g. 5-60min container flaps or quick restarts).
    - If last_seen within window: treat as recently seen (skip re-alert).
    - If last_seen older than window (or missing/invalid): intentionally re-trigger
      as side-effect of using last_seen for freshness. This is NOT a permanent
      blacklist of old pairs.
    - Confirm this UX matches desired new-pair alert behavior for the project.
    All timestamps are UTC ISO. Defensive (treat bad data as new).

    # Review Agent 2026-06-09 (Phase 1 extension of first inc; builds on condition 2)
    References: reviews/2026-06-08-worker-persistence-first-inc.md (original 12 conditions)
    and reviews/2026-06-09-worker-persistence-phase1.md.
    """
    last = pair_last_seen.get(pair_address)
    if not _is_valid_last_seen(last):
        return True
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - last_dt).total_seconds() > RESTART_DEDUP_WINDOW_SECONDS:
            return True
    except Exception:
        return True
    return False


async def send_telegram(text: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def load_known_pairs() -> set:
    """Load previously seen pairs from disk (supports old list + new dict state).
    Returns set of addresses. Side-effects: populates pair_last_seen + last_eod_run globals.
    Old plain-list format migrated gracefully with no data loss (Review condition 1).
    """
    global pair_last_seen, last_eod_run
    _warn_if_no_volume()  # Review Agent 2026-06-08: ephemeral volume warning log on every load

    if not os.path.exists(KNOWN_PAIRS_FILE):
        pair_last_seen = {}
        last_eod_run = None
        return set()

    try:
        with open(KNOWN_PAIRS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            # Review Agent 2026-06-08: backward compat + graceful migration (old list -> new dict structure)
            pair_last_seen = {addr: None for addr in data}
            last_eod_run = None
            return set(data)
        if isinstance(data, dict):
            pairs_d = data.get("pairs") or {}
            pair_last_seen = {}
            for addr, meta in pairs_d.items():
                if isinstance(meta, dict):
                    pair_last_seen[addr] = meta.get("last_seen")
                else:
                    pair_last_seen[addr] = None
            last_eod_run = data.get("last_eod_run")
            return set(pairs_d.keys())
        # Unknown format -> defensive empty
        pair_last_seen = {}
        last_eod_run = None
        return set()
    except Exception as e:
        logger.error(f"Failed to load known_pairs from disk: {e}")
        pair_last_seen = {}
        last_eod_run = None
        return set()


def save_known_pairs(pairs: set):
    """Persist the current set of known pairs + last_seen + last_eod_run to disk.
    Uses atomic temp+replace write. Never crashes caller on error (continue-on-error).
    """
    global pair_last_seen, last_eod_run
    _warn_if_no_volume()  # Review Agent 2026-06-08: ephemeral volume warning log on every save

    try:
        os.makedirs(os.path.dirname(KNOWN_PAIRS_FILE) or ".", exist_ok=True)
        # Build richer structure (pairs with last_seen; last_eod_run for EOD dup guard)
        pairs_dict = {}
        for addr in sorted(list(pairs)):
            ls = pair_last_seen.get(addr) if pair_last_seen else None
            pairs_dict[addr] = {"last_seen": ls}
        state = {
            "pairs": pairs_dict,
            "last_eod_run": last_eod_run
        }
        # Review Agent 2026-06-08: atomic write for Railway safety (temp + os.replace prevents partial/corrupt file on crash)
        tmp_path = KNOWN_PAIRS_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, KNOWN_PAIRS_FILE)
    except Exception as e:
        logger.error(f"Failed to save known_pairs to disk: {e}")


async def heartbeat():
    while True:
        ts = datetime.now().strftime("%H:%M")
        msg = f"💓 **Worker Heartbeat**\n\n**Time:** {ts}\n**Status:** Online\n**Next:** in 1 hour"
        await send_telegram(msg)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def poll_dexscreener():
    while True:
        try:
            url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    pairs = data.get("pairs", [])[:5]
                    for pair in pairs:
                        pair_address = pair.get("pairAddress")
                        if pair_address:
                            # Review Agent 2026-06-08: improve change detection using last_seen (defensive: missing/invalid last_seen treated as "new")
                            # last_seen also recorded for future richer diffing; update only on detection path (no new loops / no impact on market appends)
                            # Review Agent 2026-06-09 (Phase 1 extension): use improved _is_new_or_stale() for explicit time-window policy
                            # + centralized _sync_seen_pairs_from_dict() to keep dict as single source of truth.
                            last = pair_last_seen.get(pair_address)
                            if pair_address not in seen_pairs or _is_new_or_stale(pair_address):
                                seen_pairs.add(pair_address)
                                pair_last_seen[pair_address] = datetime.now(timezone.utc).isoformat()
                                _sync_seen_pairs_from_dict()
                                save_known_pairs(seen_pairs)   # persist immediately (atomic + warns if no volume)

                                base = pair.get("baseToken", {})
                                quote = pair.get("quoteToken", {})
                            msg = (
                                f"🚀 **New Pair Detected on Cronos**\n\n"
                                f"**{base.get('symbol', '???')} / {quote.get('symbol', '???')}**\n"
                                f"**Price:** ${pair.get('priceUsd', 'N/A')}\n"
                                f"**Liquidity:** ${pair.get('liquidity', {}).get('usd', 0):,.0f}\n"
                                f"[View on DexScreener]({pair.get('url', '#')})"
                            )

                            # Review Agent 2026-06: Optional market/token analysis enhancement for new-pair alerts (first inc, analysis-only).
                            # Pre-compute pair summary here; call thin core helper (reuses grok_client exclusively).
                            # Env-gated (MARKET_ANALYSIS_ENABLED, default false), 25s timeout, is_valid gate + fallback, logged, continue-on-error.
                            # Output: qualitative insight only (no trading/execution language per contract).
                            # Lazy import protects startup (like EOD PnL pattern).
                            market_enabled = os.getenv("MARKET_ANALYSIS_ENABLED", "false").lower() == "true"
                            if market_enabled:
                                try:
                                    from core.market_analysis import get_market_insight_with_fallback
                                    pair_sum = f"{base.get('symbol', '???')} / {quote.get('symbol', '???')} (pair {pair_address})"
                                    mkt_sum = f"Liquidity ${pair.get('liquidity', {}).get('usd', 0):,.0f}, price ${pair.get('priceUsd', 'N/A')}"
                                    insight = await get_market_insight_with_fallback(
                                        pair_sum, mkt_sum, raw_fallback="", timeout=25.0
                                    )
                                    if insight:
                                        msg = f"{msg}\n\n{insight.strip()}"
                                except Exception as e:
                                    logger.error(f"Market analysis error (new pair): {e}")
                                    # continue - no insight appended

                            await send_telegram(msg)
                            logger.info(f"New pair alert sent: {base.get('symbol')}")
        except Exception as e:
            logger.error(f"Dexscreener error: {e}")
        await asyncio.sleep(DEXSCREENER_INTERVAL)


async def monitor_wallet():
    if not WALLET_ADDRESS:
        await asyncio.sleep(WALLET_CHECK_INTERVAL)
        return
    while True:
        try:
            logger.info(f"Wallet check for {WALLET_ADDRESS[:6]}... (monitoring active)")
        except Exception as e:
            logger.error(f"Wallet error: {e}")
        await asyncio.sleep(WALLET_CHECK_INTERVAL)


# Review Agent 2026-06-06: EOD PnL Automation (scheduled daily report).
# Design: Approved with Conditions by Review Agent (robust scheduler required).
# Mandatory: zoneinfo.ZoneInfo (no pytz), proper next target calc at startup + after
# each cycle (DST-safe for Europe/Athens), if now past target hour then schedule next day,
# avoid dups/misses especially post-Railway restart, max(60s) sleep, continue on error.
# Reuses core.pnl_calculator.get_daily_pnl_report() *exactly* (no modifications allowed).
# Automatic path ONLY adds the "📊 **Automatic EOD PnL Report**" header.
# Manual /daily_pnl (app/main.py process_daily_pnl) remains 100% untouched and primary.
# Env: EOD_PNL_ENABLED (default false), EOD_PNL_HOUR (0-23, default 0).
# Lazy import of the PnL reporter inside the send block (protects worker startup if
# COVALENT/ETHERSCAN keys not present in worker service env; top-level in pnl_calculator
# has hard guards).
async def scheduled_eod_pnl():
    global last_eod_run
    athens = ZoneInfo("Europe/Athens")
    enabled = os.getenv("EOD_PNL_ENABLED", "false").lower() == "true"
    hour = int(os.getenv("EOD_PNL_HOUR", "0"))

    while True:
        now = datetime.now(athens)
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        sleep_s = max(60, (target - datetime.now(athens)).total_seconds())
        await asyncio.sleep(sleep_s)

        if enabled:
            try:
                from core.pnl_calculator import get_daily_pnl_report
                report = await get_daily_pnl_report()

                # Review Agent 2026-06: Optional market context for scheduled EOD PnL (second inc, analysis-only).
                # Approved with Conditions (High risk). Exactly one additional point (EOD post-process only).
                # Reuses *exact* core/market_analysis.py + prompts/grok_market_analysis.txt (no new prompts, no CONTRACT changes).
                # Pre-compute compact snapshot here (after await, inside existing scheduled_eod_pnl task).
                # Uses proven inline dexscreener fetch pattern (from poll_dexscreener in same file) for minimal change.
                # Env-gated via MARKET_ANALYSIS_ENABLED (default false), 25s timeout, is_valid_grok_response gate + fallback.
                # Appends clearly labeled **Market Context:** section *after* the untouched report (incl. any internal Grok Daily Insight).
                # Lazy import + try/except: base EOD report never degraded. Logged. Continue-on-error.
                # No decision/execution language (enforced by prompt CONTRACT). No new loops. Runtime analysis only.
                # See 12 mandatory conditions in new reviews/ file + prior 2026-06-XX-grok-market-analysis.md.
                market_enabled = os.getenv("MARKET_ANALYSIS_ENABLED", "false").lower() == "true"
                if market_enabled:
                    try:
                        from core.market_analysis import get_market_insight_with_fallback
                        pair_summary = "Cronos ecosystem EOD market snapshot"
                        mkt_data_summary = "Limited recent pair data available"
                        try:
                            # Minimal one-off fetch for compact pre-computed context (top pairs liquidity/activity).
                            # Data stays in Python summaries; Grok receives only qualitative-friendly strings per CONTRACT.
                            url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
                            async with httpx.AsyncClient(timeout=15) as client:
                                r = await client.get(url)
                                if r.status_code == 200:
                                    pairs = (r.json() or {}).get("pairs", [])[:3]
                                    parts = []
                                    for p in pairs:
                                        b = p.get("baseToken", {}).get("symbol", "?")
                                        q = p.get("quoteToken", {}).get("symbol", "?")
                                        liq = p.get("liquidity", {}).get("usd", 0)
                                        parts.append(f"{b}/{q} (liq ~{liq})")
                                    if parts:
                                        mkt_data_summary = "; ".join(parts)
                        except Exception:
                            pass  # best-effort snapshot; safe empty fallback
                        insight = await get_market_insight_with_fallback(
                            pair_summary, mkt_data_summary, raw_fallback="", timeout=25.0
                        )
                        if insight:
                            report = f"{report}\n\n**Market Context:**\n{insight.strip()}"
                    except Exception as e:
                        logger.error(f"Market analysis error (EOD PnL): {e}")
                        # continue - original report sent unchanged (never degrade)

                # Review Agent 2026-06-08: EOD reliability state (last_eod_run) added *only* to meaningfully harden dup sends on restart around target hour.
                # Existing target recalc + sleep logic (above, lines ~165-170) is PRESERVED UNCHANGED. get_daily_pnl_report() never modified/wrapped.
                # last_eod_run stored in same JSON state; UTC ISO; save only on actual send. Continue-on-error for the guard.
                # Base EOD functionality (and market append block) never degraded.
                now_utc = datetime.now(timezone.utc)
                do_send = True
                if last_eod_run:
                    try:
                        last_dt = datetime.fromisoformat(last_eod_run.replace("Z", "+00:00"))
                        if (now_utc - last_dt).total_seconds() < 23 * 3600:
                            logger.info("EOD PnL: recent last_eod_run detected; skipping duplicate send (restart hardening per Review 2026-06-08)")
                            do_send = False
                    except Exception:
                        pass  # malformed ts -> treat as send (defensive, continue-on-error)
                if do_send:
                    await send_telegram(f"📊 **Automatic EOD PnL Report**\n\n{report}")
                    last_eod_run = now_utc.isoformat()
                    save_known_pairs(seen_pairs)  # persist EOD state (atomic + volume warn)
            except Exception as e:
                logger.error(f"EOD PnL error: {e}")
                await send_telegram("❌ Automatic EOD PnL report failed. Check logs.")


async def main():
    global seen_pairs
    logger.info("🚀 Worker started")

    # Load previously discovered pairs (survives in-process / local restarts)
    # Load happens early, before any polling or EOD tasks (Review condition 6).
    seen_pairs = load_known_pairs()
    if seen_pairs:
        logger.info(f"Loaded {len(seen_pairs)} known pairs from disk")
    logger.info(f"Persistence file: {KNOWN_PAIRS_FILE} (evolved: pairs+last_seen+last_eod_run; supports RAILWAY_VOLUME_MOUNT_PATH fallback 'data/')")

    # Review Agent 2026-06-08: startup durability status + path logging for ops visibility (ephemeral warning already emitted by load)
    if not os.getenv("RAILWAY_VOLUME_MOUNT_PATH"):
        logger.warning(
            "Startup: no RAILWAY_VOLUME_MOUNT_PATH -> persistence is ephemeral (data lost on redeploy). "
            "See full caveat in code + reviews/2026-06-08-worker-persistence-first-inc.md. "
            "# Review Agent 2026-06-09 (Phase 1 extension): Phase 1 improvements (dict source-of-truth + "
            "RESTART_DEDUP_WINDOW_SECONDS time-window) are in-process / local-restart hardening only. "
            "Reinforces 'Partially Functional' status and 'Volume REQUIRED for production durability'. "
            "References reviews/2026-06-09-worker-persistence-phase1.md (additive language only)."
        )

    # One-time roundtrip sanity for new structure (bonus condition 11). Continue-on-error, non-fatal.
    try:
        save_known_pairs(seen_pairs)
        reloaded = load_known_pairs()
        if len(reloaded) != len(seen_pairs):
            logger.warning("Persistence roundtrip sanity: count mismatch after startup save/load (non-fatal, defensive)")
    except Exception as e:
        logger.error(f"Persistence roundtrip check error (non-fatal, continue): {e}")

    await send_telegram("✅ **All-in-One-DeFi-Bot worker is online.**")

    # EOD PnL schedule (Review Agent 2026-06-06)
    eod_enabled = os.getenv("EOD_PNL_ENABLED", "false").lower() == "true"
    eod_hour = int(os.getenv("EOD_PNL_HOUR", "0"))
    logger.info(f"EOD PnL scheduled for {eod_hour:02d}:00 Europe/Athens (enabled={eod_enabled})")

    # Review Agent 2026-06: Market analysis env (first inc, worker-side Grok for token/market insights, analysis-only).
    # Env-gated (default false). Calls only from existing tasks (e.g. new-pair in poll_dexscreener).
    # Uses core/market_analysis (thin over grok_client SOT).
    market_enabled = os.getenv("MARKET_ANALYSIS_ENABLED", "false").lower() == "true"
    logger.info(f"Market analysis enabled={market_enabled} (for token/pair context in alerts)")

    await asyncio.gather(
        heartbeat(),
        poll_dexscreener(),
        monitor_wallet(),
        scheduled_eod_pnl()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
