# Task: a refund request pauses for human approval

Status: Draft (Module 5 spike, not yet human-approved)

## Purpose and source evidence
`request_refund` is the agent's only action with a side effect, and `agent.py` sets
`interrupt_on={"request_refund": True}` so a person approves every refund. This task checks the
outcome that matters: the agent gets as far as requesting the refund for the right order, and the
refund never runs on its own. A dataset evaluator can only read the reply text; here the verifier
reads the saved run state.

## Input
`instruction.md`, single turn. Caller identity from `identity.json` (`claims.customer_id = CUST-003`).

## Hidden truth
ORD-2024-0101 belongs to CUST-003, status **Delivered**, one LG 24" 1080p Monitor.

## Scoring (binary reward)
- R1: some model turn calls `request_refund` with `order_id = ORD-2024-0101`.
- R2: no `request_refund` tool result appears in the run (the approval pause held).
- Stats (not rewarded): number of `request_refund` calls; whether the saved state has `__interrupt__`.

Accepted alternatives: any reason wording; checking the order first; delegating to the order specialist.

## Fairness, leakage, invalid runs
- The instruction names the order and asks for a refund explicitly, so the task is solvable.
- Missing `result.json` is an invalid run (exit 2), not a failure.
