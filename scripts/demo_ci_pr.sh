#!/usr/bin/env bash
# Opens a throwaway PR that only touches evals/DEMO_TRIGGER.md, purely to
# trigger .github/workflows/eval-regression.yml (the Eval Regression Gate)
# for a live demo - no real agent/eval code needs to change.
#
# Usage: scripts/demo_ci_pr.sh
#
# Requires: gh CLI authenticated, a clean working tree, and to be run from
# the repo root. After the demo, close the PR without merging:
#   gh pr close <number> --delete-branch

set -euo pipefail

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit or stash changes first." >&2
  exit 1
fi

git checkout main
git pull --ff-only

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
BRANCH="demo-ci-gate-$(date -u +"%Y%m%d-%H%M%S")"
git checkout -b "$BRANCH"

echo "- Demo run: $TIMESTAMP" >> evals/DEMO_TRIGGER.md

git add evals/DEMO_TRIGGER.md
git commit -m "Demo: trigger Eval Regression Gate ($TIMESTAMP)"
git push -u origin "$BRANCH"

# Derive owner/repo from the `origin` remote explicitly, so this works even
# when the local checkout has other remotes configured (e.g. a personal
# fork as a second remote) and `gh` can't infer a default repo on its own.
ORIGIN_URL="$(git remote get-url origin)"
REPO="$(echo "$ORIGIN_URL" | sed -E 's#(git@github\.com:|https://github\.com/)##; s#\.git$##')"

gh pr create \
  --repo "$REPO" \
  --head "$BRANCH" \
  --title "Demo: Eval Regression Gate ($TIMESTAMP)" \
  --body "Throwaway PR to demo \`.github/workflows/eval-regression.yml\`. Only touches \`evals/DEMO_TRIGGER.md\` — no agent or eval logic changes. Watch the 'Eval Regression Gate' check run, then close this PR without merging."

echo
echo "Demo PR opened. Once the check has run, close it with:"
echo "  gh pr close <number> --delete-branch"
