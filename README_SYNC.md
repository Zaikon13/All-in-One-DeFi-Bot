# 🔄 ChatGPT ↔ GitHub Full Synchronization Guide

## 1️⃣ Requirements
- ChatGPT Plus (GPT-5)
- GitHub fine-grained PAT (read/write)
- Repo installed with “ChatGPT / OpenAI” GitHub App

## 2️⃣ Required secrets (GitHub → Settings → Secrets → Actions)
GH_FINE_TOKEN
OPENAI_API_KEY
RAILWAY_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
APP_URL
TZ


## 3️⃣ Setup
1. Copy `.github/workflows/sync.yml` and `ci.yml`
2. Add `MANIFEST.md`, `SUMMARY.md`, `AGENTS.md`, `CHECKS.md`, `.env.example`
3. Enable “ChatGPT” integration at:
   https://github.com/settings/installations
4. Test with manual workflow dispatch:  
   → *Actions → ChatGPT Full Sync → Run workflow*

## 4️⃣ Validation
- ✅ CI checks should turn green
- ✅ MANIFEST auto-updates
- ✅ ChatGPT can now read/write/commit through Codex mode

## 5️⃣ Optional integrations
- Railway + Telegram for runtime reports  
- Webhook → `/telegram/webhook`
