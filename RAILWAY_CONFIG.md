# 🚂 RAILWAY CONFIGURATION — SOURCE OF TRUTH

**Project:** All-in-One-DeFi-Bot  
**Repo:** Zaikon13/All-in-One-DeFi-Bot (main branch)  
**Region:** europe-west4-drams3a (all services)  
**Last audited:** 2026-05-09

---

## 📋 SERVICE OVERVIEW

| Service | ID | Type | Purpose | Status |
|---------|-----|------|---------|--------|
| **web-GPl6** | `4ec46965-3079-435d-9755-45f49d61ae7e` | Web | FastAPI + Telegram webhook | ✅ Active |
| **bot** | `653028d3-fd57-4327-94af-27e0dd3e63b6` | Web | Duplicate FastAPI | ⚠️ Redundant |
| **worker** | `7b414e58-40b5-4771-9f77-5793d6fffae8` | Worker | Background jobs (heartbeat, PnL) | ✅ Active |

---

## 🌐 SERVICE 1: web-GPl6

**Service ID:** `4ec46965-3079-435d-9755-45f49d61ae7e`  
**Purpose:** FastAPI web server — hosts the Telegram webhook endpoint and `/health` liveness check  
**Type:** Web service (public domain)  
**Domain:** `https://web-gpl6-production.up.railway.app`  
**Port:** `8000`  
**Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"`  
**Replicas:** 1  
**Source:** `Zaikon13/All-in-One-DeFi-Bot` @ `main`

### Environment Variables

| Variable | Value | Used in Code | Notes |
|----------|-------|:------------:|-------|
| `TELEGRAM_BOT_TOKEN` | `**REDACTED**` | ✅ | `app/main.py` — sends messages, receives webhook |
| `TELEGRAM_CHAT_ID` | `5307877340` | ✅ | `app/main.py` — default chat target |
| `WALLET_ADDRESS` | `0xEa53D79ce2A915033e6b4C5ebE82bb6b292E35Cc` | ✅ | `app/main.py` — Cronos Explorer PnL query |
| `CRONOS_RPC_URL` | `https://cronos-evm-rpc.publicnode.com` | ⚠️ | Present but not yet called in `app/main.py`; reserved for future RPC calls |
| `APP_URL` | `https://web-gpl6-production.up.railway.app` | ❌ | Not read by `app/main.py`; may be used by external callers to self-reference |
| `TZ` | `Europe/Athens` | ✅ | System timezone — affects `datetime.now()` in PnL report |
| `GITHUB_APP_WEBHOOK_SECRET` | `**REDACTED**` | ✅ | `app/github_webhook.py` — HMAC validation of GitHub webhook payloads |
| `GITHUB_APP_ID` | `**REDACTED**` | ❌ | Not read in current code; reserved for GitHub App auth |
| `GITHUB_APP_INSTALLATION_ID` | `**REDACTED**` | ❌ | Not read in current code; reserved for GitHub App auth |
| `GITHUB_APP_PRIVATE_KEY_PEM` | `**REDACTED**` | ❌ | Not read in current code; reserved for GitHub App auth |
| `GH_FINE_TOKEN` | `**REDACTED**` | ❌ | Not read in current code; reserved for GitHub API calls |
| `REPO_SYNC_PAT` | `**REDACTED**` | ❌ | Not read in current code; reserved for repo sync automation |
| `GROK_API_KEY` | `**REDACTED**` | ❌ | Reserved for future Grok AI integration |
| `ETHERSCAN_API` | `**REDACTED**` | ❌ | Reserved for future Etherscan queries |
| `OPENAI_API_KEY` | `**REDACTED**` | ❌ | **DEAD — remove.** No `openai` import anywhere in codebase |
| `chatgpt_codex_All` | `**REDACTED**` | ❌ | **DEAD — remove.** No reference anywhere in codebase |

### Issues
- ❌ `OPENAI_API_KEY` — dead variable, no `openai` package in `requirements.txt`, no import in code
- ❌ `chatgpt_codex_All` — dead variable, no reference anywhere in codebase
- ✅ Telegram webhook at `/telegram/webhook` working correctly
- ✅ Health check at `/health` active
- ✅ GitHub webhook at `/webhooks/github` active with HMAC validation

---

## 🤖 SERVICE 2: bot

**Service ID:** `653028d3-fd57-4327-94af-27e0dd3e63b6`  
**Purpose:** ⚠️ **REDUNDANT** — runs the same `app.main:app` FastAPI as web-GPl6 but has no webhook registered against it  
**Type:** Web service (public domain)  
**Domain:** `https://bot-production-3d9c.up.railway.app`  
**Port:** `8000`  
**Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000`  
**Replicas:** 1  
**Source:** `Zaikon13/All-in-One-DeFi-Bot` @ `main`

### Environment Variables

| Variable | Value | Used in Code | Notes |
|----------|-------|:------------:|-------|
| `TELEGRAM_BOT_TOKEN` | `**REDACTED**` | ✅ | Same token as web-GPl6 — conflict risk if both receive updates |
| `TELEGRAM_CHAT_ID` | `5307877340` | ✅ | Same as web-GPl6 |
| `WALLET_ADDRESS` | `0xEa53D79ce2A915033e6b4C5ebE82bb6b292E35Cc` | ✅ | Same as web-GPl6 |
| `CRONOS_RPC_URL` | `https://cronos-evm-rpc.publicnode.com` | ⚠️ | Reserved, not yet used |
| `APP_URL` | `https://web-gpl6-production.up.railway.app` | ❌ | Points to web-GPl6, not itself — confirms this service is not the primary |
| `TZ` | `Europe/Athens` | ✅ | System timezone |
| `GITHUB_APP_WEBHOOK_SECRET` | `**REDACTED**` | ✅ | Same as web-GPl6 |
| `GITHUB_APP_ID` | `**REDACTED**` | ❌ | Reserved |
| `GITHUB_APP_INSTALLATION_ID` | `**REDACTED**` | ❌ | Reserved |
| `GITHUB_APP_PRIVATE_KEY_PEM` | `**REDACTED**` | ❌ | Reserved |
| `GH_FINE_TOKEN` | `**REDACTED**` | ❌ | Reserved |
| `REPO_SYNC_PAT` | `**REDACTED**` | ❌ | Reserved |
| `GROK_API_KEY` | `**REDACTED**` | ❌ | Reserved for future Grok AI integration |
| `ETHERSCAN_API` | `**REDACTED**` | ❌ | Reserved for future Etherscan queries |

### Issues
- ⚠️ **REDUNDANT** — exact duplicate of web-GPl6 with no unique purpose
- ❌ No Telegram webhook registered to this domain — it receives no traffic
- ❌ `APP_URL` points to web-GPl6, not itself — confirms it is not the primary web service
- ❌ Missing `OPENAI_API_KEY` and `chatgpt_codex_All` vs web-GPl6 (inconsistency, but both are dead anyway)
- ⚠️ Wastes Railway compute resources — **recommend deleting this service**
- ⚠️ Sharing `TELEGRAM_BOT_TOKEN` with web-GPl6 while both are running could cause duplicate message sends on startup

---

## ⚙️ SERVICE 3: worker

**Service ID:** `7b414e58-40b5-4771-9f77-5793d6fffae8`  
**Purpose:** Background job runner — 30-minute heartbeat pings, future PnL monitoring and Dexscreener polling  
**Type:** Worker service (no public domain)  
**Start Command:** `python main.py`  
**Replicas:** 1  
**Source:** `Zaikon13/All-in-One-DeFi-Bot` @ `main`

> **Note:** `railway.toml` and `Procfile` both define this service correctly.  
> `railway.toml` → `startCommand = "python -u main.py"` (with unbuffered flag)  
> `Procfile` → `worker: python -u main.py`  
> The Railway UI start command `python main.py` is missing the `-u` flag — should be aligned.

### Environment Variables

| Variable | Value | Used in Code | Notes |
|----------|-------|:------------:|-------|
| `TELEGRAM_BOT_TOKEN` | `**REDACTED**` | ✅ | `main.py` — sends heartbeat and startup messages |
| `TELEGRAM_CHAT_ID` | `5307877340` | ✅ | `main.py` — target chat for all worker messages |
| `TZ` | `Europe/Athens` | ✅ | `main.py` — logged at startup, affects `datetime.now()` in heartbeat |
| `WALLET_ADDRESS` | `0xEa53D79ce2A915033e6b4C5ebE82bb6b292E35Cc` | ⚠️ | Not yet used in `main.py`; needed for future wallet monitor |
| `CRONOS_RPC_URL` | `https://cronos-evm-rpc.publicnode.com` | ⚠️ | Not yet used in `main.py`; needed for future RPC calls |
| `ETHERSCAN_API` | `**REDACTED**` | ⚠️ | Not yet used in `main.py`; needed for future Etherscan queries |
| `GH_FINE_TOKEN` | `**REDACTED**` | ❌ | Not read in `main.py`; not needed for worker |
| `REPO_SYNC_PAT` | `**REDACTED**` | ❌ | Not read in `main.py`; not needed for worker |
| `GITHUB_APP_ID` | `**REDACTED**` | ❌ | Not read in `main.py`; not needed for worker |
| `GITHUB_APP_WEBHOOK_SECRET` | `**REDACTED**` | ❌ | Not read in `main.py`; not needed for worker |
| `GITHUB_APP_INSTALLATION_ID` | `**REDACTED**` | ❌ | Not read in `main.py`; not needed for worker |
| `GITHUB_APP_PRIVATE_KEY_PEM` | `**REDACTED**` | ❌ | Not read in `main.py`; not needed for worker |
| `APP_URL` | `https://web-gpl6-production.up.railway.app` | ❌ | **Not needed for worker** — worker has no HTTP client calls to web-GPl6 |
| `GROK_API_KEY` | `**REDACTED**` | ❌ | Reserved for future Grok AI integration |
| `OPENAI_API_KEY` | `**REDACTED**` | ❌ | **DEAD — remove.** No `openai` import in `main.py` or anywhere in codebase |
| `chatgpt_codex_All` | `**REDACTED**` | ❌ | **DEAD — remove.** No reference anywhere in codebase |

### Issues
- ❌ `OPENAI_API_KEY` — dead variable, no `openai` package in `requirements.txt`
- ❌ `chatgpt_codex_All` — dead variable, no reference anywhere in codebase
- ❌ `APP_URL` — not needed; worker does not call the web service
- ⚠️ Start command in Railway UI (`python main.py`) should be `python -u main.py` to match `railway.toml` and `Procfile`
- ✅ Heartbeat every 30 minutes working
- ✅ Startup Telegram notification working

---

## 🔍 VARIABLE USAGE AUDIT (cross-service)

### Variables used in code today

| Variable | web-GPl6 (`app/main.py`) | worker (`main.py`) | Source file |
|----------|:------------------------:|:------------------:|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | ✅ | Both |
| `TELEGRAM_CHAT_ID` | ✅ | ✅ | Both |
| `WALLET_ADDRESS` | ✅ | — | `app/main.py` |
| `TZ` | ✅ (system) | ✅ (logged) | Both |
| `GITHUB_APP_WEBHOOK_SECRET` | ✅ | — | `app/github_webhook.py` |

### Variables reserved (not yet used but intentional)

| Variable | Intended use |
|----------|-------------|
| `CRONOS_RPC_URL` | Future direct RPC calls (web + worker) |
| `WALLET_ADDRESS` | Future wallet monitor in worker |
| `ETHERSCAN_API` | Future Etherscan transaction queries |
| `GROK_API_KEY` | Future Grok AI integration |
| `GITHUB_APP_ID` | Future GitHub App JWT auth |
| `GITHUB_APP_INSTALLATION_ID` | Future GitHub App JWT auth |
| `GITHUB_APP_PRIVATE_KEY_PEM` | Future GitHub App JWT auth |
| `GH_FINE_TOKEN` | Future GitHub API calls |
| `REPO_SYNC_PAT` | Future repo sync automation |

### Dead variables — safe to delete from all services

| Variable | Reason |
|----------|--------|
| `OPENAI_API_KEY` | `openai` package not in `requirements.txt`; no import in any `.py` file |
| `chatgpt_codex_All` | No reference in any `.py` file or workflow |

---

## 🗂️ REPO FILES vs RAILWAY CONFIG ALIGNMENT

### railway.toml (current state)

```toml
[build]
builder = "DOCKERFILE"

[deploy]
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10

[[services]]
name = "worker"
type = "worker"
startCommand = "python -u main.py"
```

**Issues with current `railway.toml`:**
- ❌ Only defines the `worker` service — `web-GPl6` is not defined here
- ❌ `web-GPl6` start command is managed entirely via Railway UI, not version-controlled
- ❌ `bot` service is not defined here (consistent with it being redundant)
- ⚠️ `[build]` section applies globally but both web and worker use the same Dockerfile

### Dockerfile (current state)

```dockerfile
FROM python:3.11-slim AS builder
# ... multi-stage build ...
CMD ["python", "main.py"]
```

**Issues:**
- ❌ `CMD ["python", "main.py"]` defaults to the worker entrypoint — web-GPl6 overrides this via Railway UI start command
- ❌ `HEALTHCHECK` uses `$PORT` which is only set for web services, not worker — harmless but noisy
- ⚠️ Missing `-u` flag in `CMD` (unbuffered output); `railway.toml` and `Procfile` both use `-u`

### Procfile (current state)

```
worker: python -u main.py
```

**Notes:**
- ✅ Correct for worker
- ❌ No `web:` entry — web-GPl6 start command is Railway UI only

---

## 🎯 RECOMMENDED CLEANUP ACTIONS

### Priority 1 — Remove dead variables (all services)
- [ ] Delete `OPENAI_API_KEY` from **web-GPl6**, **worker**
- [ ] Delete `chatgpt_codex_All` from **web-GPl6**, **worker**

### Priority 2 — Remove unnecessary variables from worker
- [ ] Delete `APP_URL` from **worker** (worker never calls the web service)

### Priority 3 — Decide on `bot` service
- [ ] **Recommended: Delete the `bot` service entirely**
  - It is a duplicate of web-GPl6 with no registered Telegram webhook
  - Its `APP_URL` points to web-GPl6, confirming it is not the primary
  - Sharing `TELEGRAM_BOT_TOKEN` while both are live risks duplicate startup messages
  - No unique code, routes, or purpose distinguishes it from web-GPl6

### Priority 4 — Align railway.toml with actual services
- [ ] Add `web-GPl6` service definition to `railway.toml` so start command is version-controlled:
  ```toml
  [[services]]
  name = "web-GPl6"
  type = "web"
  startCommand = "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=\"*\""
  ```
- [ ] Fix worker start command in Railway UI to match `railway.toml`: `python -u main.py`

### Priority 5 — Fix Dockerfile CMD
- [ ] Update `CMD` to use `-u` flag for consistent unbuffered output:
  ```dockerfile
  CMD ["python", "-u", "main.py"]
  ```

### Priority 6 — Update .env.example
- [ ] Remove `OPENAI_API_KEY` from `.env.example`
- [ ] Add `GROK_API_KEY`, `ETHERSCAN_API`, `GITHUB_APP_*` variables that are now in use
- [ ] Remove stale `X_CONSUMER_*` Twitter variables (no Twitter code exists)
- [ ] Remove `RAILWAY_API_KEY` (not used in any code or workflow)

---

## ✅ MINIMUM REQUIRED VARIABLES PER SERVICE

### web-GPl6 (keep these)
```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
WALLET_ADDRESS
TZ
GITHUB_APP_WEBHOOK_SECRET
CRONOS_RPC_URL          # reserved — future RPC
GROK_API_KEY            # reserved — future Grok AI
ETHERSCAN_API           # reserved — future Etherscan
GITHUB_APP_ID           # reserved — future GitHub App
GITHUB_APP_INSTALLATION_ID  # reserved — future GitHub App
GITHUB_APP_PRIVATE_KEY_PEM  # reserved — future GitHub App
GH_FINE_TOKEN           # reserved — future GitHub API
REPO_SYNC_PAT           # reserved — future sync
APP_URL                 # self-reference, keep for external callers
```

### worker (keep these)
```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
TZ
WALLET_ADDRESS          # reserved — future wallet monitor
CRONOS_RPC_URL          # reserved — future RPC
ETHERSCAN_API           # reserved — future Etherscan
GROK_API_KEY            # reserved — future Grok AI
```

### bot (recommended: delete entire service)
If kept for any reason, it needs the same vars as web-GPl6 minus `APP_URL` (or with `APP_URL` pointing to itself).

---

## 📌 NOTES FOR GROK

1. **`app/main.py`** is the web service entrypoint. It reads: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WALLET_ADDRESS`.
2. **`app/github_webhook.py`** reads: `GITHUB_APP_WEBHOOK_SECRET`.
3. **`main.py`** (root) is the worker entrypoint. It reads: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TZ`.
4. **`core/dexscreener.py`** is a stub — no env vars read yet.
5. **`requirements.txt`** contains: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `python-telegram-bot==21.*`, `schedule`, `websockets`. No `openai` package.
6. The `bot` service has no unique code path — it runs the same `app.main:app` as web-GPl6.
7. `railway.toml` currently only covers the worker. The web service config lives entirely in the Railway UI.
8. The `DEPLOYMENT_SOP.md` file is outdated — it says "only worker should exist" but the current production setup intentionally runs web-GPl6 + worker (+ the redundant bot).
