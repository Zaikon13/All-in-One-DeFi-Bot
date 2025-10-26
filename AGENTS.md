# 🤖 AGENTS & MODULE OWNERSHIP MAP

| Module | Responsible Agent | Chat / Mode | Notes |
|--------|--------------------|--------------|--------|
| core/ | Codex | /codex_on | Core logic & PnL calculations |
| telegram/ | ChatGPT | /agent mode: Telegram | Handlers, webhook, alerts |
| reports/ | ChatGPT | /agent mode: Reports | Daily/EOD summaries |
| utils/ | ChatGPT | /code_on | HTTP, caching, helpers |
| tests/ | ChatGPT | /test mode | Unit & integration tests |
| .github/workflows/ | ChatGPT | /codex_on | CI/CD and sync automation |
