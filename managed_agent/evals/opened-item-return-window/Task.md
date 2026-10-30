# Task: return window for an opened item

Status: Draft (agent-reviewed; built end-to-end at the user's request, not yet human-approved)

## Purpose and source evidence
Policy questions are answered from the public docs that `sandbox/setup.sh` loads into
`/workspace/techhub/documents/`. This task checks that the answer is grounded in the actual
Return Policy rather than a generic "30 days" guess. Source: `instructions.md`, the
product-policy specialist, `data/documents/policies/` (return policy), and the Module 4 S3
sample "Can I return a keyboard after 20 days if I opened it?".

## Input
`instruction.md`, single turn. No order lookup is needed. `identity.json` makes the caller a
signed-in customer (CUST-003), but the question doesn't depend on it.

## Harness conditions
The full managed agent with its sandbox. Without the docs in the sandbox, the agent can only guess.

## Environment
A fresh `python:3.14-slim` container. The adapter runs `sandbox/setup.sh`, which downloads the
pinned repo commit's `data/documents/` and `products.json`. Network is needed for that download
and for the model API.

## Hidden truth
Return Policy: opened electronics can be returned within **14 days** of delivery (unopened: 30
days). A keyboard opened 20 days ago is outside the window. Defective items have a separate
route (replacement or refund, and the warranty).

## Scoring (binary reward)
- R1: the final answer names the 14-day window for opened items.
- R2: the final answer says the item isn't eligible, or is outside or past the window.
- R3 (must not happen): the answer says the customer can return it under the standard policy
  (e.g. "yes, you can return it").
- Stat: whether the answer also mentions the defective or warranty route.

Accepted alternatives: mentioning the 30-day unopened window as contrast; offering the
defective-item route.

## Fairness, leakage, invalid runs
- The policy text is agent-visible by design (it's the knowledge source). The hidden part is
  which number applies and the eligibility verdict.
- A missing result.json → invalid run. A setup.sh download failure → the adapter raises →
  Harbor infrastructure error, not reward 0.

## Open decisions
- An LLM judge for answer quality (cites "per our Return Policy"). Deterministic checks first.
