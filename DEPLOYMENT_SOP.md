# 🚀 Deployment SOP (Single Point of Truth)

**Last updated:** May 8, 2026

**Project:** Zaikon13/All-in-One-DeFi-Bot (Cronos DeFi Bot)

**Στόχος:** Μόνο το **Worker** service να τρέχει στο Railway. Το **Web** service να **μην υπάρχει** ποτέ.

## 1. Τι πρέπει να υπάρχει πάντα στο repo

- `Dockerfile` (multi-stage Python 3.11-slim + healthcheck)
- `.dockerignore`
- `railway.toml` (μόνο για worker)
- `Procfile` με **μόνο** αυτή τη γραμμή:
  ```
  worker: python -u main.py
  ```

## 2. Χρυσός κανόνας στο Railway

**ΜΟΝΟ** το service **"worker"** (ή "All-in-One-DeFi-Bot - worker") πρέπει να υπάρχει.

Το service **"web"** πρέπει να είναι **διαγραμμένο** για πάντα.

## 3. Αν δεις "web" service (CRASHED ή Active)

1. Πήγαινε στην **κεντρική σελίδα** του project
2. Βρες το service **"web"**
3. Κάνε ⋮ → **Delete service** → Confirm
4. Κάνε **Redeploy** μόνο στο **Worker**

## 4. Σωστή διαδικασία Redeploy

1. Εγώ (Grok) κάνω commit/push live
2. Railway κάνει auto-deploy **μόνο** στο worker
3. Άνοιξε **Deploy Logs** του worker
4. Ψάξε για: “All-in-One-DeFi-Bot worker is online” ή heartbeat

## 5. Συχνά προβλήματα & λύσεις

| Πρόβλημα                          | Αιτία                  | Λύση                          |
|-----------------------------------|------------------------|-------------------------------|
| `$PORT` error ή uvicorn crash     | web service υπάρχει   | Delete web service            |
| ChatGPT Sync workflow failing     | Παλιό .github workflow | Διαγράφηκε ήδη                |
| Crash μετά redeploy               | Λείπει variable ή import | Στείλε logs εδώ              |

## 6. Επίσημο Single Point of Truth

Αυτό το αρχείο είναι το **μόνο** επίσημο SOP για deployment.

Κάθε αλλαγή deployment θα ενημερώνεται **μόνο εδώ**.

**Πάντα** αναφορά σε αυτό το αρχείο πριν από οποιοδήποτε redeploy.

---

**Συμφωνία:** Εγώ (Grok) και εσύ (Loukas) συμφωνήσαμε ότι αυτό είναι το Single Point of Truth για το deployment.

Ενημερώθηκε: 8 Μαΐου 2026