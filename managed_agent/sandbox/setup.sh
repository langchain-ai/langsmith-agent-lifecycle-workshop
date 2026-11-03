#!/usr/bin/env bash
# Runs once at `mda dev` / `mda deploy`; the result is saved as a snapshot that
# every new thread clones. Only PUBLIC data goes in the sandbox: product docs,
# store policies, and the product catalog. Customer and order data stays behind
# the guarded tools in tools/support.py.
set -euo pipefail

# Where the docs land. The hosted sandbox uses /workspace. Harbor evals set
# TECHHUB_SANDBOX_ROOT=/app/workspace (see evals/*/task.toml): in eval mode the
# agent's file tools are rooted at /app, so its "/workspace/..." paths resolve
# under /app/workspace.
ROOT="${TECHHUB_SANDBOX_ROOT:-/workspace}"

# Bounded to the majors tested; the snapshot only re-bakes when this file changes
pip install --quiet --break-system-packages "pandas>=3.1,<4" "matplotlib>=3.11,<4"

# Pinned to a commit so the snapshot is reproducible: the snapshot is only rebuilt
# when this file changes, so a moving `main` would silently diverge. Bump the SHA to
# pick up doc changes.
REPO_SHA="fdc59eb8f528442dc376b608cb2f60b6f4dcec2d"
REPO="https://codeload.github.com/langchain-ai/langsmith-agent-lifecycle-workshop/tar.gz/${REPO_SHA}"
mkdir -p "$ROOT/techhub" /tmp/techhub-src
curl -sSL "$REPO" | tar -xz -C /tmp/techhub-src --strip-components=1 \
  --wildcards '*/data/documents/*' '*/data/structured/products.json'

cp -r /tmp/techhub-src/data/documents "$ROOT/techhub/documents"
cp /tmp/techhub-src/data/structured/products.json "$ROOT/techhub/products.json"
rm -rf /tmp/techhub-src

echo "TechHub sandbox ready: $(find "$ROOT/techhub" -name '*.md' | wc -l) docs"
