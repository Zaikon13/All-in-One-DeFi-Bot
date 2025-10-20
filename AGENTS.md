# AGENTS.md — All-in-One-DeFi-Bot

## Purpose
Repo-first κανόνες για Codex/ChatGPT. Όλες οι προτάσεις/patches είναι πλήρη αρχεία (όχι diffs) και δουλεύουμε μόνο πάνω στο τρέχον repo.

## Process (PR flow)
1) Δημιουργία branch στο GitHub Web UI.
2) Copy-paste πλήρη αρχεία στους σωστούς paths.
3) Open Pull Request προς `main`.
4) Πρέπει να περάσει το required check **CI** (import smoke + pytest).
5) Merge → (προαιρετικά) Railway PR Environments για preview.

## Policies
- Κανένα secret στο repo (χρήση GitHub Actions **Secrets** μόνο).
- Branch protection: Require PR + Require status checks (CI).
- Σταθερότητα: Μικρά, εστιασμένα PRs. Αν αλλάζει ροή, το δηλώνουμε ρητά.
- Deliverables: Πλήρη αρχεία, deploy-ready. Όχι placeholders.

## Notes
- Το `ci.yml` κάνει import smoke των modules `main` και `app` και τρέχει pytest αν υπάρχει `tests/`.
- Αν προστεθούν νέα modules που πρέπει να φορτώνονται στο import smoke, ενημέρωσε τη λίστα στο workflow.
