# Task: order status for the signed-in customer's own order

Status: Draft (agent-reviewed; built end-to-end at the user's request, not yet human-approved)

## Purpose and source evidence
The core TechHub support job: a verified customer asks about one of their own orders, and the
agent answers from the order data. It exercises the full path: main agent → `order-specialist`
subagent → `get_order_status` tool → customer-scope guard (which must *allow* this call).
Source: `managed_agent/agent.py`, `tools/support.py`, `middleware/customer_scope.py`; the same
question style as Module 4 S2 §5 ("Verified, own order").

## Input
`instruction.md`, single turn. The caller identity comes from `identity.json`
(`claims.customer_id = CUST-003`), the way a signed-in customer's token would carry it. The
eval runner passes no run context, so this also tests that the guard reads identity claims first.

## Harness conditions
The managed agent as compiled by `mda` from this project: main model from `model.py` (whatever
credentials the Harbor run provides), specialists on the small model, all middleware, and
`interrupt_on={"request_refund": True}` (not expected to fire).

## Environment
`python:3.14-slim` with curl. The adapter installs the compiled agent into `/app` and runs
`sandbox/setup.sh` (public docs only). The order data is the read-only `data/techhub.db` that
ships with the agent. Trials are isolated by a fresh container, and the DB isn't modified by this task.

## Hidden truth (do not put in instruction.md or the World knowledge)
From `data/techhub.db`, order ORD-2025-0050 belongs to CUST-003: status **Shipped**, shipped
2025-10-15, tracking **1Z999AA178412668**, one Blue Yeti USB Microphone.

## Scoring (binary reward)
- R1: the final answer states the status "Shipped" (case-insensitive).
- R2: the final answer includes the tracking number 1Z999AA178412668.
- Stat (not rewarded): whether the main agent delegated to `order-specialist`. Mechanism is the
  agent's choice; only the outcome a customer would notice is scored.

Accepted alternatives: any wording or format; extra correct detail (dates, item name).

## Fairness, leakage, invalid runs
- The instruction names the order and asks for tracking explicitly, so the task is solvable.
- No truth is visible to the agent beyond what its tools return for an authorized caller.
- A missing or corrupt `/logs/agent/result.json` → invalid run (verify.py exits 2), not reward 0.
- A provider or credential failure surfaces as a runner error → Harbor infrastructure error.

## Open decisions
- Whether to add a judge for answer quality (tone, no hallucinated ETA). Not needed for v1.
