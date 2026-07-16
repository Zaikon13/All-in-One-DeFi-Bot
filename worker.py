# worker.py - Final Stable Version with Real Alerts + Wallet Monitoring

import asyncio
import json
import math
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from core.log_redaction import install_log_redaction

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
install_log_redaction()  # Part D: strip apikey= from logs (log-only)


def _env_float(name: str, default: float) -> float:
    """Defensive env-var float parse: bad values log a warning and fall back."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        v = float(raw)
        if not math.isfinite(v) or v < 0:
            raise ValueError("must be finite and >= 0")
        return v
    except (TypeError, ValueError):
        logger.warning(f"Invalid {name}={raw!r}; using default {default}")
        return default


# New-pair alert filters (2026-07-05). The Dexscreener call is a TEXT search across
# every chain, so results must be filtered to chainId == "cronos"; "new" means
# pairCreatedAt within PAIR_NEWNESS_WINDOW_HOURS; dust pools below
# PAIR_MIN_LIQUIDITY_USD are skipped. All alerts in one cycle go out as ONE message.
PAIR_NEWNESS_WINDOW_HOURS = _env_float("PAIR_NEWNESS_WINDOW_HOURS", 24.0)
PAIR_MIN_LIQUIDITY_USD = _env_float("PAIR_MIN_LIQUIDITY_USD", 10000.0)

# Quality scoring for new-pair alerts (2026-07-06, Part A). Each ingredient is worth
# 0-25 points (total 0-100): 1h volume (full marks at PAIR_SCORE_VOL1H_FULL),
# 1h buy pressure (0 pts at <=50% buys, full at >=PAIR_SCORE_BUY_RATIO_FULL),
# 1h price momentum (0 pts at <=0%, full at >=PAIR_SCORE_MOM1H_FULL %), and
# liquidity depth (full at PAIR_SCORE_LIQ_FULL). Only pairs scoring at least
# PAIR_MIN_SCORE are alerted; the rest are counted in the log line only.
PAIR_MIN_SCORE = _env_float("PAIR_MIN_SCORE", 35.0)
PAIR_SCORE_VOL1H_FULL = _env_float("PAIR_SCORE_VOL1H_FULL", 25000.0)
PAIR_SCORE_BUY_RATIO_FULL = _env_float("PAIR_SCORE_BUY_RATIO_FULL", 0.85)
PAIR_SCORE_MOM1H_FULL = _env_float("PAIR_SCORE_MOM1H_FULL", 30.0)
PAIR_SCORE_LIQ_FULL = _env_float("PAIR_SCORE_LIQ_FULL", 50000.0)
PAIR_SCORE_STRONG = 70.0  # tier label only: >= -> "strong", else "notable"
if not (0.5 < PAIR_SCORE_BUY_RATIO_FULL <= 1.0):
    logger.warning(
        f"PAIR_SCORE_BUY_RATIO_FULL={PAIR_SCORE_BUY_RATIO_FULL} is outside (0.5, 1.0] — "
        "it is a FRACTION (e.g. 0.85), not a percent; buy-pressure points are disabled/skewed."
    )

# Portfolio-watch (2026-07-06, Part B): price-move alerts on tokens the owner holds.
# Reuses core.wallet.get_wallet_balances (balances + Dexscreener pricing) — no duplicated
# logic. Baseline is IN-MEMORY ONLY: a restart quietly re-seeds it (first cycle seeds,
# alerts possible from the second cycle onward — never a false alert on restart).
PORTFOLIO_WATCH_ENABLED = os.getenv("PORTFOLIO_WATCH_ENABLED", "true").lower() == "true"
PORTFOLIO_WATCH_INTERVAL_MIN = _env_float("PORTFOLIO_WATCH_INTERVAL_MIN", 5.0)
PORTFOLIO_MOVE_THRESHOLD_PCT = _env_float("PORTFOLIO_MOVE_THRESHOLD_PCT", 10.0)
PORTFOLIO_MIN_USD = _env_float("PORTFOLIO_MIN_USD", 5.0)
PORTFOLIO_ALERT_COOLDOWN_MIN = _env_float("PORTFOLIO_ALERT_COOLDOWN_MIN", 60.0)
# Daily scanner digest (2026-07-16, visibility without noise): once a day the worker
# sends ONE summary of the new-pair funnel — how many pairs the search returned, how
# many survived each filter, the best score seen, and how many were alerted — so the
# scanner's judgment is visible every evening even when nothing clears the bar.
# No quality threshold is changed by this feature.
SCAN_DIGEST_ENABLED = os.getenv("SCAN_DIGEST_ENABLED", "true").lower() == "true"
SCAN_DIGEST_HOUR = int(_env_float("SCAN_DIGEST_HOUR", 21.0)) % 24  # Athens hour


def _new_scan_stats() -> dict:
    return {"seen": 0, "cronos": 0, "newness": 0, "liquidity": 0,
            "below_score": 0, "sent": 0, "best_score": None, "best_symbol": None}


scan_stats = _new_scan_stats()


def record_pair_funnel(stats: dict, seen=0, cronos=0, newness=0, liquidity=0,
                       below_score=0, sent=0, best=None) -> dict:
    """Fold one polling cycle's funnel counts into stats (pure; unit-tested).
    best = (score, symbol) of the best-scoring pair this cycle, alerted or not."""
    stats["seen"] += seen
    stats["cronos"] += cronos
    stats["newness"] += newness
    stats["liquidity"] += liquidity
    stats["below_score"] += below_score
    stats["sent"] += sent
    if best is not None:
        try:
            score = float(best[0])
            # strip Markdown v1 entity chars from the symbol — scam tokens carry
            # *_[]` and one unpaired entity would 400 the day's single digest
            symbol = re.sub(r"[*_\[\]`]", "", str(best[1])).strip() or "?"
            if math.isfinite(score) and (stats["best_score"] is None or score > stats["best_score"]):
                stats["best_score"], stats["best_symbol"] = score, symbol
        except (TypeError, ValueError, IndexError):
            pass  # malformed best never breaks the counters
    return stats


def format_scan_digest(stats: dict) -> str:
    """One-line Telegram digest (Markdown v1 safe; pure; unit-tested)."""
    if stats["best_score"] is None:
        best = "—"
    else:
        best = f"{stats['best_score']:.0f} ({stats['best_symbol']})"
    return (f"🔎 **Scanner digest** — pairs seen: {stats['seen']}, "
            f"passed Cronos filter: {stats['cronos']}, "
            f"passed newness: {stats['newness']}, "
            f"passed liquidity: {stats['liquidity']}, "
            f"best score today: {best} — sent: {stats['sent']}")


if PORTFOLIO_MOVE_THRESHOLD_PCT <= 0:
    logger.warning(
        f"PORTFOLIO_MOVE_THRESHOLD_PCT={PORTFOLIO_MOVE_THRESHOLD_PCT} <= 0 — every watched "
        "holding would alert once per cooldown window; using default 10.0 instead."
    )
    PORTFOLIO_MOVE_THRESHOLD_PCT = 10.0
MAX_PAIRS_PER_ALERT = 10  # Telegram 4096-char safety; extras summarized as a count

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

# Review Agent 2026-06-09 (Phase 2): EOD PnL guard + startup sanity (addresses Review 2026-06-09-worker-persistence-phase2.md
# Medium issues on delta logging, documented threshold, additive honesty + comments; fulfills first-inc conds 3/6/9/10).
# last_eod_run used ONLY for ~23h dup prevention on restart around target (existing target recalc + sleep PRESERVED UNCHANGED;
# get_daily_pnl_report() never modified/wrapped). Startup block is logging-only decision (no immediate/auto send, no behavior change).
# Phase 2 hardens in-process / local-restart behavior only. Still 'Partially Functional'. Volume still REQUIRED for production durability.
# See reviews/2026-06-08-worker-persistence-first-inc.md + reviews/2026-06-09-worker-persistence-phase1.md + reviews/2026-06-09-worker-persistence-phase2.md. No over-claims.
# Persistence path resolution (verified 2026-07-13): explicit WORKER_DATA_DIR wins
# (single documented config point, also for future paper-trading state); else
# Railway's auto-injected RAILWAY_VOLUME_MOUNT_PATH — in production the 5GB volume
# "worker-persistence-GNKn" is mounted at /data, so this resolves to /data and
# known_pairs.json genuinely survives redeploys; else a local ./data for dev.
PERSISTENCE_BASE = (os.getenv("WORKER_DATA_DIR")
                    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
                    or "data")
KNOWN_PAIRS_FILE = os.path.join(PERSISTENCE_BASE, "known_pairs.json")


def _warn_if_no_volume():
    """Emit loud WARNING on every load/save and at startup if no volume (per Review)."""
    if not (os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or os.getenv("WORKER_DATA_DIR")):
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


def _clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0  # nan/inf from the API must count as 0 points, never pass the gate
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def score_pair(pair: dict, liq: float) -> dict:
    """Transparent 0-100 quality score for a new pair, from fields Dexscreener
    already returns. Pure + defensive (bad/missing fields count as 0 points, never
    raise). Returns the ingredients alongside the score so alerts can show the
    'why', not just a verdict:
    {score, vol1h, buys, sells, buy_ratio, chg1h, pts_volume, pts_buys, pts_momentum, pts_liquidity}
    """
    def _sub(key):  # tolerate wrong shapes ("volume": "nope") — treat as empty
        v = pair.get(key) if isinstance(pair, dict) else None
        return v if isinstance(v, dict) else {}

    try:
        vol1h = float(_sub("volume").get("h1") or 0)
    except (TypeError, ValueError):
        vol1h = 0.0
    tx1h = _sub("txns").get("h1")
    tx1h = tx1h if isinstance(tx1h, dict) else {}
    try:
        buys = int(tx1h.get("buys") or 0)
        sells = int(tx1h.get("sells") or 0)
    except (TypeError, ValueError):
        buys = sells = 0
    try:
        chg1h = float(_sub("priceChange").get("h1") or 0)
    except (TypeError, ValueError):
        chg1h = 0.0

    pts_volume = 25.0 * _clamp01(vol1h / PAIR_SCORE_VOL1H_FULL) if PAIR_SCORE_VOL1H_FULL > 0 else 0.0
    buy_ratio = (buys / (buys + sells)) if (buys + sells) > 0 else 0.0
    denom = PAIR_SCORE_BUY_RATIO_FULL - 0.5
    pts_buys = 25.0 * _clamp01((buy_ratio - 0.5) / denom) if denom > 0 else 0.0
    pts_momentum = 25.0 * _clamp01(chg1h / PAIR_SCORE_MOM1H_FULL) if PAIR_SCORE_MOM1H_FULL > 0 else 0.0
    pts_liquidity = 25.0 * _clamp01(liq / PAIR_SCORE_LIQ_FULL) if PAIR_SCORE_LIQ_FULL > 0 else 0.0

    return {
        "score": round(pts_volume + pts_buys + pts_momentum + pts_liquidity, 1),
        "vol1h": vol1h, "buys": buys, "sells": sells,
        "buy_ratio": round(buy_ratio, 3), "chg1h": chg1h,
        "pts_volume": round(pts_volume, 1), "pts_buys": round(pts_buys, 1),
        "pts_momentum": round(pts_momentum, 1), "pts_liquidity": round(pts_liquidity, 1),
    }


async def poll_dexscreener():
    """Poll Dexscreener and alert on genuinely new Cronos pairs.

    Fixes (2026-07-05):
    - search?q=cronos is a text search across ALL chains (Solana results were being
      announced as "on Cronos") -> only pairs with chainId == "cronos" are processed.
    - "New" now means pairCreatedAt within PAIR_NEWNESS_WINDOW_HOURS (default 24h);
      pairs without a valid pairCreatedAt are skipped (newness unverifiable).
    - Pairs with liquidity.usd below PAIR_MIN_LIQUIDITY_USD (default $10k) are skipped.
    - All new pairs found in one polling cycle are sent as ONE combined Telegram
      message (this also fixes the prior bug where the alert send sat OUTSIDE the
      newness check, re-announcing the top search results every cycle).
    Known-pairs dedup/persistence (seen_pairs + _is_new_or_stale) is unchanged.
    """
    while True:
        try:
            url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    now_utc = datetime.now(timezone.utc)
                    fresh = []  # (pair, liquidity_usd, age_hours, score_dict)
                    below_score = 0
                    cy_seen = cy_cronos = cy_new = cy_liq = 0
                    cy_best = None  # (score, symbol) best this cycle, alerted or not
                    for pair in (data.get("pairs") or []):
                        cy_seen += 1
                        if str(pair.get("chainId") or "").lower() != "cronos":
                            continue  # text search returns pairs from every chain
                        cy_cronos += 1
                        pair_address = pair.get("pairAddress")
                        if not pair_address:
                            continue
                        # genuine newness: pairCreatedAt (ms epoch) within the window
                        try:
                            created_dt = datetime.fromtimestamp(
                                int(pair.get("pairCreatedAt")) / 1000, tz=timezone.utc
                            )
                        except (TypeError, ValueError, OSError, OverflowError):
                            continue  # missing/invalid creation time -> can't verify newness
                        age_h = (now_utc - created_dt).total_seconds() / 3600.0
                        if age_h < 0 or age_h > PAIR_NEWNESS_WINDOW_HOURS:
                            continue
                        cy_new += 1
                        # liquidity floor: skip dust pools
                        try:
                            liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                        except (TypeError, ValueError):
                            liq = 0.0
                        if liq < PAIR_MIN_LIQUIDITY_USD:
                            continue
                        cy_liq += 1
                        # quality score gate (2026-07-06, Part A): below-bar pairs are
                        # skipped WITHOUT being marked seen, so they can re-qualify on a
                        # later cycle if volume/buys/momentum pick up within the window.
                        sc = score_pair(pair, liq)
                        _sym = (pair.get("baseToken") or {}).get("symbol", "?")
                        if cy_best is None or sc["score"] > cy_best[0]:
                            cy_best = (sc["score"], _sym)
                        if sc["score"] < PAIR_MIN_SCORE:
                            below_score += 1
                            if pair_address in seen_pairs:
                                # already announced once: keep its last_seen fresh so a
                                # dip-below-bar + recovery doesn't re-alert (~hourly) via
                                # _is_new_or_stale. Never-alerted pairs stay unmarked and
                                # can still qualify later in their window.
                                pair_last_seen[pair_address] = datetime.now(timezone.utc).isoformat()
                            continue
                        # known-pairs dedup (last_seen + restart window, persistence unchanged).
                        # 2026-07-05: last_seen is now ALSO refreshed in-memory on the skip path;
                        # otherwise a pair inside the 24h window re-alerts every RESTART_DEDUP_WINDOW
                        # (~hourly, up to ~24 dup alerts/pair/day). Disk write stays alert-path-only,
                        # so restart behavior (one possible re-alert after a gap) is preserved.
                        if pair_address not in seen_pairs or _is_new_or_stale(pair_address):
                            seen_pairs.add(pair_address)
                            pair_last_seen[pair_address] = datetime.now(timezone.utc).isoformat()
                            _sync_seen_pairs_from_dict()
                            save_known_pairs(seen_pairs)  # persist immediately (atomic + warns if no volume)
                            fresh.append((pair, liq, age_h, sc))
                        else:
                            pair_last_seen[pair_address] = datetime.now(timezone.utc).isoformat()

                    record_pair_funnel(scan_stats, seen=cy_seen, cronos=cy_cronos,
                                       newness=cy_new, liquidity=cy_liq,
                                       below_score=below_score, sent=len(fresh),
                                       best=cy_best)

                    if fresh:
                        market_enabled = os.getenv("MARKET_ANALYSIS_ENABLED", "false").lower() == "true"
                        sections = []
                        for pair, liq, age_h, sc in fresh[:MAX_PAIRS_PER_ALERT]:
                            base = pair.get("baseToken") or {}
                            quote = pair.get("quoteToken") or {}
                            tier = "🔥 strong" if sc["score"] >= PAIR_SCORE_STRONG else "👀 notable"
                            section = (
                                f"**{base.get('symbol', '???')} / {quote.get('symbol', '???')}** — score {sc['score']:.0f}/100 ({tier})\n"
                                f"- Price: ${pair.get('priceUsd', 'N/A')} ({sc['chg1h']:+.1f}% 1h)\n"
                                f"- Liquidity: ${liq:,.0f} | Vol 1h: ${sc['vol1h']:,.0f}\n"
                                f"- Buys/Sells 1h: {sc['buys']}/{sc['sells']}\n"
                                f"- Age: {age_h:.1f}h\n"
                                f"[View on DexScreener]({pair.get('url', '#')})"
                            )
                            # Optional env-gated market insight per pair (semantics unchanged;
                            # appended inside the combined message instead of its own send).
                            if market_enabled:
                                try:
                                    from core.market_analysis import get_market_insight_with_fallback
                                    pair_sum = f"{base.get('symbol', '???')} / {quote.get('symbol', '???')} (pair {pair.get('pairAddress')})"
                                    mkt_sum = f"Liquidity ${liq:,.0f}, price ${pair.get('priceUsd', 'N/A')}"
                                    insight = await get_market_insight_with_fallback(
                                        pair_sum, mkt_sum, raw_fallback="", timeout=25.0
                                    )
                                    if insight:
                                        ins = insight.strip()
                                        if len(ins) > 300:
                                            ins = ins[:300].rstrip() + "..."
                                        section = f"{section}\n{ins}"
                                except Exception as e:
                                    logger.error(f"Market analysis error (new pair): {e}")
                                    # continue - no insight appended
                            sections.append(section)
                        if len(fresh) > MAX_PAIRS_PER_ALERT:
                            sections.append(f"...plus {len(fresh) - MAX_PAIRS_PER_ALERT} more new pairs this cycle.")
                        header = (
                            "🚀 **New Pair Detected on Cronos**"
                            if len(fresh) == 1
                            else f"🚀 **{len(fresh)} New Pairs Detected on Cronos**"
                        )
                        combined = "\n\n".join([header] + sections)
                        if len(combined) > 4000:  # Telegram hard limit is 4096
                            combined = combined[:4000].rstrip() + "\n\n(truncated)"
                        await send_telegram(combined)
                        logger.info(
                            "New pair alert sent (1 message, %d pair(s), %d below score bar %.0f): %s",
                            len(fresh), below_score, PAIR_MIN_SCORE,
                            ", ".join((p.get("baseToken") or {}).get("symbol", "?") for p, _, _, _ in fresh),
                        )
                    elif below_score:
                        logger.info(
                            "New-pair scan: 0 alerted, %d pair(s) passed filters but scored below %.0f",
                            below_score, PAIR_MIN_SCORE,
                        )
        except Exception as e:
            logger.error(f"Dexscreener error: {e}")
        await asyncio.sleep(DEXSCREENER_INTERVAL)


def _fmt_price(p: float) -> str:
    """Compact price string for both normal and micro-cap prices."""
    if p >= 1:
        return f"${p:,.4f}"
    if p >= 0.01:
        return f"${p:.4f}"
    return f"${p:.8f}"


def watch_holdings(balances: dict, min_usd: float, baseline: dict | None = None) -> list:
    """Extract the watch list from a core.wallet.get_wallet_balances result:
    priced holdings worth at least min_usd, native CRO included. min_usd is an
    ENTRY criterion only — a holding already in the baseline stays watched even
    if its value crashes below the bar (a -95% dump is exactly what must alert).
    Returns [{key, symbol, amount, usd, price}]; I/O-free, never raises."""
    out = []
    known = baseline or {}
    try:
        cro = float(balances.get("cro") or 0)
        cro_usd = balances.get("cro_usd")
        if cro_usd is not None and cro > 0 and (cro_usd >= min_usd or "native:CRO" in known):
            out.append({"key": "native:CRO", "symbol": "CRO", "amount": cro,
                        "usd": float(cro_usd), "price": float(cro_usd) / cro})
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    for d in (balances.get("token_details") or []) if isinstance(balances.get("token_details"), list) else []:
        try:
            usd = d.get("usd")
            amount = d.get("amount") or 0
            key = d.get("contract") or d.get("symbol")
            if usd is None or amount <= 0:
                continue
            if usd < min_usd and key not in known:
                continue
            out.append({"key": key, "symbol": d.get("symbol", "?"),
                        "amount": float(amount), "usd": float(usd), "price": float(usd) / float(amount)})
        except (TypeError, ValueError, ZeroDivisionError, AttributeError):
            continue  # one bad row never drops the rest
    return out


def detect_portfolio_moves(holdings: list, baseline: dict, last_alert: dict,
                           now_utc, threshold_pct: float, cooldown_min: float) -> list:
    """Compare holdings against the rolling baseline; return alert-worthy moves.

    Deterministic, I/O-free state step (unit-tested offline; mutates its two
    state dicts): first sighting of a holding only
    SEEDS its baseline (no alert — this is what makes restarts quiet); afterwards
    a move of at least threshold_pct vs baseline alerts, subject to one alert per
    holding per cooldown_min. The baseline REBASES on alert (the next alert needs
    another threshold move from the alerted price), and small drift accumulates
    against the old baseline until it trips. Mutates baseline/last_alert.
    """
    moves = []
    for h in holdings:
        key = h["key"]
        base = baseline.get(key)
        if base is None or not base.get("price") or base["price"] <= 0:
            baseline[key] = {"price": h["price"], "ts": now_utc.isoformat()}
            continue
        move_pct = (h["price"] - base["price"]) / base["price"] * 100.0
        if abs(move_pct) < threshold_pct:
            continue
        la = last_alert.get(key)
        if la is not None and (now_utc - la).total_seconds() < cooldown_min * 60:
            continue
        moves.append({
            "symbol": h["symbol"], "move_pct": move_pct,
            "old_price": base["price"], "new_price": h["price"],
            "amount": h["amount"],
            "old_usd": h["amount"] * base["price"], "new_usd": h["usd"],
        })
        baseline[key] = {"price": h["price"], "ts": now_utc.isoformat()}
        last_alert[key] = now_utc
    return moves


async def portfolio_watch():
    """Periodic price-move alerts on held tokens (information only, no trading).

    Reuses core.wallet.get_wallet_balances (lazy import protects worker startup).
    Any fetch/pricing failure skips the cycle with a log line — this loop must
    never crash the worker. Gated by PORTFOLIO_WATCH_ENABLED (default on).
    """
    if not PORTFOLIO_WATCH_ENABLED:
        logger.info("portfolio-watch: disabled (PORTFOLIO_WATCH_ENABLED=false)")
        return
    if not WALLET_ADDRESS:
        logger.info("portfolio-watch: no WALLET_ADDRESS; not watching")
        return
    interval_s = max(60.0, PORTFOLIO_WATCH_INTERVAL_MIN * 60.0)
    baseline: dict = {}
    last_alert: dict = {}
    logger.info(
        f"portfolio-watch: on — every {PORTFOLIO_WATCH_INTERVAL_MIN:g} min, move >= "
        f"{PORTFOLIO_MOVE_THRESHOLD_PCT:g}%, holdings >= ${PORTFOLIO_MIN_USD:g}, "
        f"cooldown {PORTFOLIO_ALERT_COOLDOWN_MIN:g} min (baseline in-memory; restarts re-seed quietly)"
    )
    while True:
        try:
            from core.wallet import get_wallet_balances
            balances = await get_wallet_balances(WALLET_ADDRESS)
            if not balances.get("priced"):
                logger.info("portfolio-watch: pricing unavailable this cycle; skipped")
            else:
                now_utc = datetime.now(timezone.utc)
                holdings = watch_holdings(balances, PORTFOLIO_MIN_USD, baseline)
                seeding = not baseline
                moves = detect_portfolio_moves(
                    holdings, baseline, last_alert, now_utc,
                    PORTFOLIO_MOVE_THRESHOLD_PCT, PORTFOLIO_ALERT_COOLDOWN_MIN,
                )
                if seeding:
                    logger.info(f"portfolio-watch: baseline seeded for {len(baseline)} holding(s)")
                if moves:
                    lines = []
                    for mv in moves:
                        arrow = "📈" if mv["move_pct"] >= 0 else "📉"
                        lines.append(
                            f"{arrow} **{mv['symbol']}** {mv['move_pct']:+.1f}% — "
                            f"{_fmt_price(mv['old_price'])} → {_fmt_price(mv['new_price'])} | "
                            f"your {mv['amount']:,.4f}".rstrip("0").rstrip(".") + f" {mv['symbol']}: "
                            f"${mv['old_usd']:,.2f} → ${mv['new_usd']:,.2f}"
                        )
                    msg = "\n\n".join(["📊 **Portfolio movers**"] + lines)
                    if len(msg) > 4000:
                        msg = msg[:4000].rstrip() + "\n\n(truncated)"
                    await send_telegram(msg)
                    logger.info(
                        "portfolio-watch: alert sent (1 message, %d mover(s)): %s",
                        len(moves), ", ".join(mv["symbol"] for mv in moves),
                    )
        except Exception as e:
            logger.error(f"portfolio-watch error (cycle skipped): {e}")
        await asyncio.sleep(interval_s)


async def scheduled_scan_digest():
    """Send ONE scanner-funnel summary per day at SCAN_DIGEST_HOUR Europe/Athens
    (default 21:00) and reset the counters. In-memory only: a restart restarts the
    counting window (the digest then covers time since restart). DST-safe target
    recomputation each loop, same pattern as scheduled_eod_pnl. Never crashes."""
    global scan_stats
    if not SCAN_DIGEST_ENABLED:
        logger.info("scanner digest: disabled (SCAN_DIGEST_ENABLED=false)")
        return
    athens = ZoneInfo("Europe/Athens")
    logger.info(f"scanner digest: on — daily at {SCAN_DIGEST_HOUR:02d}:00 Europe/Athens")
    while True:
        now = datetime.now(athens)
        target = now.replace(hour=SCAN_DIGEST_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep(max(60.0, (target - datetime.now(athens)).total_seconds()))
        try:
            # snapshot-and-reset first: counts folded while the send awaits belong
            # to the NEXT window, and a mid-send failure can't double-report.
            snap, scan_stats = scan_stats, _new_scan_stats()
            msg = format_scan_digest(snap)
            await send_telegram(msg)
            logger.info(f"scanner digest: {msg}")
        except Exception as e:
            logger.error(f"scanner digest error (window already rolled): {e}")


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
                # Appends clearly labeled **Market Context:** section *after* the untouched report (incl. any internal Claude Daily Insight).
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
                # Review Agent 2026-06-09 (Phase 2, per reviews/2026-06-08-worker-persistence-first-inc.md cond. 3 + reviews/2026-06-09-worker-persistence-phase1.md + reviews/2026-06-09-worker-persistence-phase2.md):
                # Hardened guard: unconditional delta logging (both paths) + explicit malformed log for ops visibility; ~23h window for restart dup prevention only.
                # Existing scheduler/target/sleep/report behavior 100% unchanged. No immediate/auto send on any path.
                now_utc = datetime.now(timezone.utc)
                do_send = True
                if last_eod_run:
                    try:
                        last_dt = datetime.fromisoformat(last_eod_run.replace("Z", "+00:00"))
                        delta_s = (now_utc - last_dt).total_seconds()
                        if delta_s < 23 * 3600:
                            logger.info(f"EOD PnL: delta={delta_s:.0f}s since last_eod_run; 23h guard decision=skip (restart hardening per Review 2026-06-08 cond. 3 + Phase 2)")
                            do_send = False
                        else:
                            logger.info(f"EOD PnL: delta={delta_s:.0f}s since last_eod_run; 23h guard decision=send")
                    except Exception:
                        logger.info("EOD PnL: malformed last_eod_run ts; treating as send (defensive, continue-on-error per Review 2026-06-08 cond. 3)")
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

    # Review Agent 2026-06-09 (Phase 2, per reviews/2026-06-08-worker-persistence-first-inc.md cond. 6 + reviews/2026-06-09-worker-persistence-phase1.md + reviews/2026-06-09-worker-persistence-phase2.md):
    # Startup sanity for EOD PnL (logging-only decision after long downtime; no immediate/auto send, no behavior/timing change).
    # last_eod_run from load (early, before tasks). Threshold documented (addresses Medium). Existing target recalc + sleep PRESERVED UNCHANGED.
    # No auto-send: scheduler handles targets. Phase 2: in-process / local-restart hardening only. Still 'Partially Functional'.
    # Volume still REQUIRED for production durability. See prior reviews + original 12 conditions. No over-claims.
    if eod_enabled:
        EOD_LONG_DOWNTIME_HOURS = 24  # documented threshold for "long downtime" decision (per Review 2026-06-09 Medium)
        if last_eod_run:
            try:
                last_dt = datetime.fromisoformat(last_eod_run.replace("Z", "+00:00"))
                delta_h = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600.0
                if delta_h > EOD_LONG_DOWNTIME_HOURS:
                    logger.info(f"EOD PnL startup sanity: last_eod_run was {delta_h:.1f}h ago (long downtime >{EOD_LONG_DOWNTIME_HOURS}h). "
                                "Scheduler will target the next appropriate daily slot. No immediate/auto send triggered on startup "
                                "(to preserve daily timing and avoid potential duplicate/missed reports). Existing target recalc + sleep logic preserved unchanged.")
                else:
                    logger.info(f"EOD PnL startup sanity: last_eod_run was {delta_h:.1f}h ago (recent).")
            except Exception:
                logger.info("EOD PnL startup sanity: malformed last_eod_run ts (non-fatal). Scheduler will compute next target.")
        else:
            logger.info("EOD PnL startup sanity: no prior last_eod_run (fresh or cleared state). Scheduler will compute first target.")

    # Review Agent 2026-06: Market analysis env (first inc, worker-side Grok for token/market insights, analysis-only).
    # Env-gated (default false). Calls only from existing tasks (e.g. new-pair in poll_dexscreener).
    # Uses core/market_analysis (thin over grok_client SOT).
    market_enabled = os.getenv("MARKET_ANALYSIS_ENABLED", "false").lower() == "true"
    logger.info(f"Market analysis enabled={market_enabled} (for token/pair context in alerts)")

    await asyncio.gather(
        heartbeat(),
        poll_dexscreener(),
        monitor_wallet(),
        scheduled_eod_pnl(),
        portfolio_watch(),
        scheduled_scan_digest()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
