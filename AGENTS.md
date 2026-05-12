# 🤖 AGENTS & MODULE OWNERSHIP MAP

**Last Updated:** 12 Μαΐου 2026

| Module / Area          | Responsible Agent | Notes |
|------------------------|-------------------|-------|
| Deployment & Railway   | Grok              | DEPLOYMENT_SOP.md, RAILWAY.md, webhook fixes |
| Worker Loop (`main.py` + `core/`) | Grok         | Full DeFi logic, Dexscreener, PnL, alerts |
| Telegram handlers      | Grok / ChatGPT    | Webhook, /daily_pnl |
| core/PnL & calculations| Codex / Grok      | Refactor pending |
| Tests & CI             | Grok              | Integration tests next |
| Documentation          | Grok              | SUMMARY, CHECKS, AGENTS, SOP |

**Current Focus:** Grok is leading the Worker Loop implementation.