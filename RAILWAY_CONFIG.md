# 🚂 RAILWAY CONFIGURATION — SOURCE OF TRUTH

**Project:** All-in-One-DeFi-Bot  
**Repo:** Zaikon13/All-in-One-DeFi-Bot (main branch)  
**Region:** europe-west4-drams3a (all services)  
**Last audited:** 2026-05-09

---

## 📋 SERVICE OVERVIEW

| Service | ID | Type | Purpose | Status |
|---------|-----|------|---------|--------|
| **bot** | `653028d3-fd57-4327-94af-27e0dd3e63b6` | Web | FastAPI + Telegram webhook | ✅ Active (Telegram webhook) |
| **web-GPl6** | `4ec46965-3079-435d-9755-45f49d61ae7e` | Web | Duplicate FastAPI | ⚠️ Redundant |
| **worker** | `7b414e58-40b5-4771-9f77-5793d6fffae8` | Worker | Background jobs (heartbeat, PnL) | ✅ Active |

---

## 🌐 SERVICE 1: bot

**Service ID:** `653028d3-fd57-4327-94af-27e0dd3e63b6`  
**Purpose:** FastAPI web server — hosts the Telegram webhook endpoint  
**Type:** Web service (public domain)  
**Domain:** `https://bot-production-3d9c.up.railway.app`  
**Port:** `8000`  
**Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000`  
**Replicas:** 1  
**Source:** `Zaikon13/All-in-One-DeFi-Bot` @ `main`  
**Status:** ✅ ACTIVE — Telegram webhook registered and responding

### Environment Variables

| Variable | Value | Used in Code | Notes |
|----------|-------|:------------:|-------|
| `TELEGRAM_BOT_TOKEN` | `**REDACTED**` | ✅ | `app/main.py` — sends messages, receives webhook |
| `TELEGRAM_CHAT_ID` | `5307877340` | ✅ | `app/main.py` — default chat target |
| `WALLET_ADDRESS` | `0xEa53D79ce2A915033e6b4C5ebE82bb6b292E35Cc` | ✅ | `app/main.py` — Cronos Explorer PnL query |
| `CRONOS_RPC_URL` | `https://cronos-evm-rpc.publicnode.com` | ⚠️ | Present but not yet called in `app/main.py`; reserved for future RPC calls |
| `APP_URL` | `https://bot-production-3d9c.up.railway.app` | ❌ | Not read by `app/main.py`; self-reference URL |
| `TZ` | `Europe/Athens` | ✅ | System timezone — affects `datetime.now()` in PnL report |
| `GITHUB_APP_WEBHOOK_SECRET` | `**REDACTED**` | ❌ | Dead variable — not referenced anywhere in Python source |
| `OPENAI_API_KEY` | `**REDACTED**` | ❌ | Dead variable — OpenAI integration removed; not called in `app/main.py` |
| `chatgpt_codex_All` | `**REDACTED**` | ❌ | Dead variable — unknown purpose; not referenced in source |

---

## 🌐 SERVICE 2: web-GPl6

**Service ID:** `4ec46965-3079-435d-9755-45f49d61ae7e`  
**Purpose:** ⚠️ REDUNDANT — runs the same FastAPI as bot but has no webhook registered  
**Type:** Web service (public domain)  
**Domain:** `https://web-gpl6-production.up.railway.app`  
**Port:** `8000`  
**Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"`  
**Replicas:** 1  
**Source:** `Zaikon13/All-in-One-DeFi-Bot` @ `main`  
**Status:** ⚠️ REDUNDANT — no Telegram webhook registered; recommend deletion

### Environment Variables

| Variable | Value | Used in Code | Notes |
|----------|-------|:------------:|-------|
| `TELEGRAM_BOT_TOKEN` | `**REDACTED**` | ✅ | Same token as bot — but no webhook points here |
| `TELEGRAM_CHAT_ID` | `5307877340` | ✅ | Same as bot |
| `WALLET_ADDRESS` | `0xEa53D79ce2A915033e6b4C5ebE82bb6b292E35Cc` | ✅ | Same as bot |
| `CRONOS_RPC_URL` | `https://cronos-evm-rpc.publicnode.com` | ⚠️ | Reserved; not yet called |
| `APP_URL` | `https://web-gpl6-production.up.railway.app` | ❌ | Points to itself (web-GPl6), not to bot — confirms this service is self-contained and unused |
| `TZ` | `Europe/Athens` | ✅ | System timezone |
| `GITHUB_APP_WEBHOOK_SECRET` | `**REDACTED**` | ❌ | Dead variable |
| `OPENAI_API_KEY` | `**REDACTED**` | ❌ | Dead variable |
| `chatgpt_codex_All` | `**REDACTED**` | ❌ | Dead variable |

---

## ⚙️ SERVICE 3: worker

**Service ID:** `7b414e58-40b5-4771-9f77-5793d6fffae8`  
**Purpose:** Background job runner — heartbeat pings and scheduled PnL reports  
**Type:** Worker (no public domain)  
**Domain:** None  
**Port:** N/A  
**Start Command:** `python -u main.py`  
**Replicas:** 1  
**Source:** `Zaikon13/All-in-One-DeFi-Bot` @ `main`  
**Status:** ✅ Active

### Environment Variables

| Variable | Value | Used in Code | Notes |
|----------|-------|:------------:|-------|
| `TELEGRAM_BOT_TOKEN` | `**REDACTED**` | ✅ | `main.py` — sends heartbeat and PnL messages |
| `TELEGRAM_CHAT_ID` | `5307877340` | ✅ | `main.py` — target chat for scheduled messages |
| `WALLET_ADDRESS` | `0xEa53D79ce2A915033e6b4C5ebE82bb6b292E35Cc` | ✅ | `main.py` — Cronos Explorer PnL query |
| `CRONOS_RPC_URL` | `https://cronos-evm-rpc.publicnode.com` | ⚠️ | Reserved for future RPC calls |
| `TZ` | `Europe/Athens` | ✅ | System timezone |
| `OPENAI_API_KEY` | `**REDACTED**` | ❌ | Dead variable — not referenced in `main.py` |
| `chatgpt_codex_All` | `**REDACTED**` | ❌ | Dead variable |

---

## 🔍 VARIABLE USAGE AUDIT

### Summary across all services

| Variable | bot | web-GPl6 | worker | Verdict |
|----------|-----|----------|--------|---------|
| `TELEGRAM_BOT_TOKEN` | ✅ Active | ⚠️ Set but unused (no webhook) | ✅ Active | Keep in bot + worker; remove from web-GPl6 on deletion |
| `TELEGRAM_CHAT_ID` | ✅ Active | ⚠️ Set but unused | ✅ Active | Keep in bot + worker |
| `WALLET_ADDRESS` | ✅ Active | ⚠️ Set but unused | ✅ Active | Keep in bot + worker |
| `CRONOS_RPC_URL` | ⚠️ Reserved | ⚠️ Reserved | ⚠️ Reserved | Keep — future RPC integration |
| `APP_URL` | ❌ Dead | ❌ Dead (points to web-GPl6 itself) | N/A | Remove from both web services |
| `TZ` | ✅ Active | ⚠️ Set but unused | ✅ Active | Keep in bot + worker |
| `GITHUB_APP_WEBHOOK_SECRET` | ❌ Dead | ❌ Dead | N/A | Remove from all services |
| `OPENAI_API_KEY` | ❌ Dead | ❌ Dead | ❌ Dead | Remove from all services |
| `chatgpt_codex_All` | ❌ Dead | ❌ Dead | ❌ Dead | Remove from all services |

### Key finding
**bot** is the PRIMARY Telegram webhook handler. The webhook URL `https://bot-production-3d9c.up.railway.app/telegram/webhook` is registered with Telegram and actively receiving messages. **web-GPl6** runs identical code but has no webhook registered — it is a redundant duplicate that should be deleted.

---

## ⚠️ MISALIGNMENTS DETECTED

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `railway.toml` only defines `worker` service | `railway.toml` | bot and web-GPl6 are configured via Railway UI only, not in code |
| 2 | `APP_URL` in web-GPl6 points to itself, not to bot | web-GPl6 env vars | Confirms web-GPl6 is self-contained and not the active webhook handler |
| 3 | `OPENAI_API_KEY` and `chatgpt_codex_All` set on all services | All services | Dead variables — OpenAI integration was removed; wastes secret storage |
| 4 | `GITHUB_APP_WEBHOOK_SECRET` set on bot and web-GPl6 | bot, web-GPl6 | Dead variable — not referenced in any Python source file |
| 5 | web-GPl6 uses `--proxy-headers` flag; bot does not | Start commands | Inconsistency — bot is the active service and works without proxy headers |

---

## ✅ RECOMMENDED CLEANUP ACTIONS

### Priority 1 — Remove dead variables (all services)
Delete `OPENAI_API_KEY`, `chatgpt_codex_All`, and `GITHUB_APP_WEBHOOK_SECRET` from bot, web-GPl6, and worker. These are not referenced in any Python source file.

### Priority 2 — Remove APP_URL (both web services)
`APP_URL` is not read by `app/main.py`. Remove it from both bot and web-GPl6.

### Priority 3 — Delete web-GPl6 service
**web-GPl6 is the redundant duplicate and should be deleted.** The active Telegram webhook is registered to `https://bot-production-3d9c.up.railway.app/telegram/webhook` — this is the **bot** service. web-GPl6 runs the same code but has no webhook registered and its `APP_URL` points to itself, confirming it is unused. Deleting web-GPl6 eliminates the duplicate and reduces Railway resource usage.

### Priority 4 — Align railway.toml with actual services
Add bot service definition to `railway.toml` so the active web service is tracked in code, not just in the Railway UI.

---

## 📦 MINIMUM REQUIRED VARIABLES PER SERVICE

### bot (PRIMARY — keep all)
```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
WALLET_ADDRESS
CRONOS_RPC_URL   # reserved
TZ
```

### web-GPl6 (REDUNDANT — recommend deletion)
This service should be deleted entirely. It is a duplicate of bot with no webhook registered.

### worker (keep as-is)
```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
WALLET_ADDRESS
CRONOS_RPC_URL   # reserved
TZ
```

---

*This file is the single source of truth for Railway service configuration. Update after any infrastructure change.*
