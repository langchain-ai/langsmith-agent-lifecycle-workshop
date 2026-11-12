# CI Demo Trigger

This file exists solely so we can demo `.github/workflows/eval-regression.yml`
(the Eval Regression Gate) without touching real agent or evaluator code.

Run `scripts/demo_ci_pr.sh` to open a throwaway PR that appends a timestamp
below and triggers the gate. It's safe to close the PR without merging once
you're done demoing — nothing in this file affects the agent or the dataset.

## Demo log
- PR #34 gate trigger: 2026-10-14T17:42:14Z
- PR #38 gate trigger: 2026-11-04T11:23:32Z
- 2026-11-04: Module 6 mda init cell path fix (run the required eval check)
- PR #40 gate trigger: 2026-11-12T22:38:45Z (Module 6 harbor --no-project fix; notebook and README only, so the required eval check needs this)
