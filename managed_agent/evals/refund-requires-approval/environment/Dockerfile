# The MDA Harbor adapter installs the compiled agent into /app and runs sandbox/setup.sh,
# which needs curl, tar, and bash. Nothing task-specific is visible to the agent.
# Python matches the compiled artifact (python_version in mda-eval-manifest.json).
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl tar bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
