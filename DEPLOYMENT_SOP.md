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

**Αυτό το SOP είναι το μοναδικό επίσημο reference point.**

**Current State Locked:** Webhook confirmed working on bot-production-3d9c.up.railway.app