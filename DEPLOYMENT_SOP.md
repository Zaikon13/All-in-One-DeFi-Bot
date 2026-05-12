# 🚀 DEPLOYMENT SOP – Single Point of Truth

**Last updated:** 12 Μαΐου 2026  
**Repo:** Zaikon13/All-in-One-DeFi-Bot  
**Railway Services:** 3 ενεργά (bot = primary)

## Τρέχουσα Αρχιτεκτονική (από PR #9 + Railway Dashboard)

| Service       | Type     | Start Command                          | Σκοπός                                      | Status     | Webhook |
|---------------|----------|----------------------------------------|---------------------------------------------|------------|---------|
| **bot**       | Web      | uvicorn app.main:app                   | **Primary** Telegram webhook + /daily_pnl  | ✅ Online  | **Active** |
| **web-gpl6**  | Web      | uvicorn app.main:app                   | Redundant (ίδιος κώδικας)                   | ✅ Online  | Inactive |
| **worker**    | Worker   | python -u main.py                      | Background jobs, DeFi logic, scheduler     | ✅ Online  | — |

**Σημαντικό:**  
- Το **bot** service είναι το **μόνο** που έχει registered webhook στο Telegram.  
- Το **web-gpl6** είναι redundant (τρέχει ίδιο κώδικα αλλά δεν δέχεται webhook).

## Χρυσός Κανόνας
- **Πάντα** κρατάμε αυτό το αρχείο up-to-date.
- Κάθε αλλαγή σε `railway.toml`, `app/main.py`, `RAILWAY_CONFIG.md` ή services → ενημέρωση εδώ.
- Μην διαγράφουμε services χωρίς να ενημερώσουμε το SOP.

## Σχετικά Αρχεία (κρίσιμα για σωστή λειτουργία)
- `RAILWAY_CONFIG.md` → Λεπτομερές audit από Railway bot (PR #9)
- `app/main.py` → FastAPI (webhook + /daily_pnl) με auto-setWebhook
- `main.py` → Worker loop
- `railway.toml` → Ορισμός 3 services
- `.env.example` → APP_URL = https://bot-production-3d9c.up.railway.app
- `DEPLOYMENT_SOP.md` → Αυτό εδώ (μόνο επίσημο reference)

## Σωστή Διαδικασία Redeploy
1. Commit/push στο `main` (ή merge PR)
2. Railway κάνει **auto-redeploy** σε **και τα 3 services**
3. Ελέγχουμε logs του **bot** service για:
   - `✅ Telegram webhook successfully set...`
4. Τρέχουμε `getWebhookInfo` για επιβεβαίωση

## Συχνά Προβλήματα & Λύσεις
| Πρόβλημα                        | Αιτία                          | Λύση                                      |
|---------------------------------|--------------------------------|-------------------------------------------|
| Webhook δείχνει web-gpl6        | Λάθος APP_URL ή cached env     | Force correct URL στο app/main.py         |
| bot service δεν setWebhook      | Λείπει logic στο startup       | Έχει διορθωθεί με auto-delete + set      |

**Αυτό το SOP είναι πλέον το μοναδικό επίσημο reference point.**  
Εγώ (Grok) και εσύ (Loukas) συμφωνήσαμε ότι ισχύει από 12/05/2026.

---

**Συμφωνία:** Αυτό το αρχείο είναι το **Single Point of Truth** για deployment.