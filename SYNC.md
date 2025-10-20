# SYNC — Source of Truth

Κανόνες:
1) Repo-first: όλα μέσω PRs (Web UI).
2) SPOT υπερισχύει: README/SUMMARY/SYNC/CHECKS/DEPLOY/RAILWAY = αλήθεια.
3) Κανένα secret στο repo (μόνο Actions Secrets & Railway Variables).
4) Μικρά, στοχευμένα PRs. Πράσινο CI πάντα.

Checks πριν/μετά:
- PR καθαρό diff, χωρίς secrets
- CI green
- Railway logs OK (Web/Worker)
- `getWebhookInfo` OK

2-Service Deploy:
- **Web**: Procfile → `web: uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}`
- **Worker**: Start Command (Railway UI) → `python -u worker.py`
