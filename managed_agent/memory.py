"""Durable memory for this deployment."""

from managed_deepagents import MemoryLayer, define_memory

# Memory is opt-in: without this file the agent keeps nothing between runs.
#
# Enable agent and user memory independently with
# `agent=MemoryLayer()` and `user=MemoryLayer()`.
# Omitted layers are disabled. Agent memory is shared across callers at
# `/memories/agent/`. User memory requires identity and defaults to managed
# Slack one-to-one DMs at `/memories/user/`. Either layer can provide an
# `allow(context)` policy. Each tree is read/write; its `AGENTS.md` is hot
# memory and other files are read on demand.
#
# The agent layer is a trust boundary. Because runs can write hot memory and hot
# memory is injected into every later run, whatever one caller gets the agent to
# save is read by everyone after them — instructions included. Treat memory as
# untrusted input, keep authority (tool access, approvals) in agent.py rather than
# in memory, and mount no agent layer if your callers should not influence
# each other.
#
# The content lives in LangSmith Context Hub, not in this file: deploys never
# overwrite what earlier runs learned.


def ops_only(context: object) -> bool:
    """Mount shared agent memory only for operations runs (schedules, the ops team).

    Customer conversations never mount it, so one customer can't plant notes
    (or instructions) that the next customer's run would load. The policy runs
    once per run, before storage mounts; returning False skips the mount and
    deletes nothing.
    """
    role = context.get("role") if isinstance(context, dict) else getattr(context, "role", None)
    return role == "ops"


memory = define_memory(agent=MemoryLayer(allow=ops_only))
