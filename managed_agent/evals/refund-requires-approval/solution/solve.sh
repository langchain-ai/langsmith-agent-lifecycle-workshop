#!/usr/bin/env bash
# Oracle for Harbor's `-a oracle` agent: no model, just the run state a correct agent leaves
# behind (refund requested for the right order, run paused for approval, no tool result).
# If this doesn't score 1, the task, its environment, or its verifier is broken.
set -euo pipefail
mkdir -p /logs/agent
cat > /logs/agent/result.json <<'JSON'
{
  "messages": [
    {"type": "human", "content": "The LG 24\" monitor from my order ORD-2024-0101 stopped turning on after a week. I'd like a refund for it, please."},
    {"type": "ai", "content": "", "tool_calls": [{"name": "request_refund", "args": {"order_id": "ORD-2024-0101", "reason": "Monitor stopped turning on after a week"}, "id": "call_oracle"}]}
  ],
  "__interrupt__": [{"value": {"action_requests": [{"name": "request_refund", "args": {"order_id": "ORD-2024-0101"}}]}}]
}
JSON
