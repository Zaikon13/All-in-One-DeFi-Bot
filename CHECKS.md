# CHECKS

Pre-PR
- [ ] No secrets
- [ ] Updated docs if flow changes
- [ ] `python -m compileall .` OK (locally)

Post-merge
- [ ] Railway deploy OK (Web/Worker)
- [ ] `/health` 200
- [ ] Webhook POSTs 200 in logs
- [ ] Tag/version noted

Next (when features land)
- [ ] /holdings, /totals, /pnl handlers
- [ ] Wallet monitor / Dexscreener polling
- [ ] Guards, thresholds (env-driven)
- [ ] EOD daily report task on Worker
