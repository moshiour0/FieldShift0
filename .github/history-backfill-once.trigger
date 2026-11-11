One-time marker for the 12 November 2026 FieldShift NASA POWER history backfill.

On the first merge containing this file on main, .github/workflows/history-backfill.yml runs its existing preflight and archives all nine reference points for 2016–2025. A normal subsequent push will not trigger another backfill unless this marker file itself is changed again.

The workflow still has its manual workflow_dispatch entry point. The preflight validates the four existing Google Drive Actions secrets and performs a Drive read-back test before it requests NASA POWER data.