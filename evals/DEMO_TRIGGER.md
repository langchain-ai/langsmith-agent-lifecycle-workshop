# CI Demo Trigger

This file exists solely so we can demo `.github/workflows/eval-regression.yml`
(the Eval Regression Gate) without touching real agent or evaluator code.

Run `scripts/demo_ci_pr.sh` to open a throwaway PR that appends a timestamp
below and triggers the gate. It's safe to close the PR without merging once
you're done demoing — nothing in this file affects the agent or the dataset.

## Demo log
