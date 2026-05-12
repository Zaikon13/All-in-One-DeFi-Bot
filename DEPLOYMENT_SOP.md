# 🚀 DEPLOYMENT SOP – Single Point of Truth

**Last updated:** 12 Μαΐου 2026  
**Repo:** Zaikon13/All-in-One-DeFi-Bot  
**Railway Services:** 3 ενεργά (bot = primary)

## Τρέχουσα Αρχιτεκτονική

| Service       | Type     | Start Command                          | Σκοπός                                      | Status     | Webhook |
|---------------|----------|----------------------------------------|---------------------------------------------|------------|---------|
| **bot**       | Web      | uvicorn app.main:app                   | **Primary** Telegram webhook + /daily_pnl  | ✅ Online  | **Active** |
| **web-gpl6**  | Web      | uvicorn app.main:app                   | Redundant (ίδιος κώδικας)                   | ✅ Online  | Inactive |
| **worker**    | Worker   | python -u main.py                      | Background jobs, DeFi logic, scheduler     | ✅ Online  | — |

**Σημαντικό:** Το **bot** service είναι το **μόνο** που έχει registered webhook στο Telegram.

**Current State:** Webhook confirmed working on https://bot-production-3d9c.up.railway.app/telegram/webhook

**This SOP is the single source of truth.** All documentation has been synced to match the current stable working state.

**Locked:** 12 Μαΐου 2026