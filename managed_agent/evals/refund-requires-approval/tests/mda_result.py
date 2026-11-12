"""Read the MDA eval runner's output for a Harbor verifier.

The MDA Harbor adapter runs the agent in the task container and writes the final graph
state to /logs/agent/result.json (messages as dicts). Verifiers read that file; it is
independent of anything the agent writes into its workspace.

Exit codes used by verify.py: 0 = pass, 1 = fail (agent work), 2 = invalid run
(no evidence, so it is not the agent's fault).

report() also writes /logs/verifier/reward.json: the overall `reward` plus one 0/1 score per
check. Harbor prefers reward.json over reward.txt, and the LangSmith plugin turns each key
into a feedback score, so a failed run shows which check failed.
"""

import json
import os
import re
import sys
from pathlib import Path

# Overridable only for local verifier tests; Harbor uses the defaults.
RESULT = Path(os.environ.get("MDA_EVAL_RESULT", "/logs/agent/result.json"))
INVALID = Path(os.environ.get("MDA_EVAL_INVALID", "/logs/verifier/invalid.txt"))
REWARD = Path(os.environ.get("MDA_EVAL_REWARD", "/logs/verifier/reward.json"))


def invalid(reason: str) -> None:
    INVALID.parent.mkdir(parents=True, exist_ok=True)
    INVALID.write_text(reason + "\n")
    print(f"INVALID: {reason}")
    sys.exit(2)


def load_messages() -> list[dict]:
    if not RESULT.is_file():
        invalid(f"{RESULT} missing: the agent runner did not finish")
    try:
        state = json.loads(RESULT.read_text())
    except json.JSONDecodeError as e:
        invalid(f"{RESULT} is not valid JSON: {e}")
    messages = state.get("messages") if isinstance(state, dict) else None
    if not isinstance(messages, list) or not messages:
        invalid("result.json has no messages")
    return messages


def text_of(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def role_of(message: dict) -> str:
    return message.get("type") or message.get("role") or ""


def final_answer(messages: list[dict]) -> str:
    for message in reversed(messages):
        if role_of(message) in ("ai", "assistant") and text_of(message).strip():
            return text_of(message)
    return ""


def tool_calls(messages: list[dict]) -> list[dict]:
    return [call for m in messages if role_of(m) in ("ai", "assistant") for call in (m.get("tool_calls") or [])]


def everything_after_the_question(messages: list[dict]) -> str:
    """All model and tool text except the user's own message (for leak checks)."""
    return "\n".join(text_of(m) for m in messages if role_of(m) not in ("human", "user"))


def report(checks: dict[str, bool], reward_keys: list[str], stats: dict | None = None) -> None:
    for name, ok in checks.items():
        tag = "reward" if name in reward_keys else "stat"
        print(f"[{'PASS' if ok else 'FAIL'}] {name} ({tag})")
    for name, value in (stats or {}).items():
        print(f"[stat] {name}: {value}")
    passed = all(checks[k] for k in reward_keys)
    rewards = {"reward": float(passed)}
    rewards |= {re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"): float(ok) for name, ok in checks.items()}
    REWARD.parent.mkdir(parents=True, exist_ok=True)
    REWARD.write_text(json.dumps(rewards) + "\n")
    sys.exit(0 if passed else 1)
