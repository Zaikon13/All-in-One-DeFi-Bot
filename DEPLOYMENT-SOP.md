# Cronos DeFi Bot - Deployment SOP (Single Point of Truth)

**Last Updated:** May 8, 2026

Αυτό είναι το **επίσημο Single Point of Truth** για το deployment του All-in-One-DeFi-Bot στο Railway.

## Στόχος
- Μόνο το **Worker** service να τρέχει (Telegram polling bot)
- Το **Web** service να είναι **διαγραμμένο** για πάντα

## Τρέχουσα Απαιτούμενη Δομή

### Αρχεία που πρέπει να υπάρχουν στη ρίζα:
- `Dockerfile` (multi-stage)
- `.dockerignore`
- `railway.toml`
- `Procfile`

### Procfile (Πρέπει να περιέχει μόνο αυτό)
```procfile
worker: python -u main.py
```

## Κανόνες Χρυσού

1. **Ποτέ** μην αφήνεις το service **"web"** να υπάρχει στο Railway
2. Μόνο το **"worker"** service επιτρέπεται
3. Κάθε φορά που βλέπεις "web" service → **Διάγραψέ το αμέσως**

## Πώς να κάνεις Redeploy σωστά

1. Κάνω εγώ (Grok) push στο `main` branch
2. Το Railway κάνει auto-deploy στο **Worker**
3. Ελέγχουμε τα **Deploy Logs** του Worker service
4. Ψάχνουμε για επιτυχημένη εκκίνηση ("Bot is online", heartbeat κλπ.)

## Συχνά Προβλήματα & Λύσεις

| Πρόβλημα | Αιτία | Λύση |
|----------|-------|------|
| `web` service CRASHED | Υπάρχει web service με uvicorn/app.main | Διάγραψε το web service |
| `$PORT` is not valid integer | Web service | Διάγραψε το web service |
| 502 errors / webhook | Web service προσπαθεί να τρέξει | Διάγραψε το web service |
| ChatGPT Sync failing | Παλιό workflow | Έχει ήδη διαγραφεί |

## Επίσημη Διαδικασία Delete Web Service

1. Πήγαινε στην **κεντρική σελίδα** του Railway project
2. Βρες το service **"web"**
3. Κάνε κλικ στα **⋯** (τρεις τελείες) δεξιά
4. Επίλεξε **Delete service** → Confirm
5. Κάνε Redeploy στο **Worker** service

---

**Αυτό το αρχείο είναι Single Point of Truth.**
Κάθε αλλαγή στο deployment θα ενημερώνεται εδώ.

**Owner:** Zaikon13 + Grok (Cronos DeFi Bot Team)