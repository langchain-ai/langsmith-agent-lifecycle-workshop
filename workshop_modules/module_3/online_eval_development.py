"""Plumbing for the Section 1a data-flywheel notebook.

The notebook keeps the *flywheel-defining* SDK calls inline and visible
(`create_feedback`, `create_annotation_queue`, `add_runs_to_annotation_queue`,
`create_dataset`, `evaluate`) because those are the lesson. The mechanical
plumbing — driving multi-turn conversations through the HITL agent, rendering
transcripts, building LangSmith UI links, and polling for a thread's anchor run
— lives here so the notebook reads cleanly, mirroring how Module 2 imports its
agents and evaluators instead of redefining them.

All functions take their dependencies (agent, client, ids) as explicit
arguments so there is no hidden global state.
"""

import asyncio
import time
import uuid

from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.types import Command

# ============================================================================
# 2. Generate "production" traffic
# ============================================================================


async def run_conversation(agent, turns: list[str]) -> tuple[str, list]:
    """Run one multi-turn conversation through the agent in a single thread.

    Handles the agent's HITL email interrupt by feeding the next scripted turn
    in as the ``resume`` value. Returns ``(thread_id, final_messages)``.

    We hand back the agent's own final message list so the judge can score the
    conversation straight from memory: LangSmith indexes run *outputs* a beat
    behind run creation, so re-fetching them immediately can come back empty.
    The thread/run records themselves are available right away.
    """
    thread_id = str(uuid.uuid4())
    # Tag every run so this synthetic demo traffic is easy to find (and filter
    # out) in the shared workshop project.
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {"demo": "online-eval-1a"},
    }
    next_input = {"messages": [{"role": "user", "content": turns[0]}]}
    i = 1
    result = {}

    while True:
        result = await agent.ainvoke(next_input, config=config)

        if result.get("__interrupt__"):
            # Agent paused to ask for the customer's email (HITL).
            if i >= len(turns):
                break
            next_input = Command(resume=turns[i])
            i += 1
            continue

        # Turn finished normally; send the next user turn if there is one.
        if i >= len(turns):
            break
        next_input = {"messages": [{"role": "user", "content": turns[i]}]}
        i += 1

    return thread_id, result.get("messages", [])


async def run_conversations(agent, conversations: list[list[str]]) -> tuple[list[str], dict]:
    """Run several conversations concurrently (each is an independent thread).

    Returns ``(thread_ids, messages_by_thread)`` and flushes traces before
    returning so the caller can immediately query the runs back from LangSmith.
    """
    results = await asyncio.gather(
        *(run_conversation(agent, convo) for convo in conversations)
    )
    thread_ids = [tid for tid, _ in results]
    messages_by_thread = {tid: msgs for tid, msgs in results}

    # Traces upload in the background; flush before anyone queries them back.
    wait_for_all_tracers()
    return thread_ids, messages_by_thread


def format_conversation(messages: list) -> str:
    """Render a transcript as ``User:`` / ``Assistant:`` lines.

    Handles both LangChain message objects (in-memory) and the plain dicts
    LangSmith returns.
    """
    lines = []
    for m in messages:
        if isinstance(m, dict):
            role, content = m.get("role") or m.get("type"), m.get("content")
        else:
            role, content = getattr(m, "type", None), getattr(m, "content", None)
        if not content or not isinstance(content, str):
            continue
        if role in ("human", "user"):
            lines.append(f"User: {content}")
        elif role in ("ai", "assistant"):
            lines.append(f"Assistant: {content}")
    return "\n".join(lines)


# ============================================================================
# Thread anchoring + UI links
# ============================================================================


def thread_url(client, tenant_id: str, project_id: str, thread_id: str) -> str:
    """Link straight to the multi-turn conversation (thread) view in LangSmith."""
    return f"{client._host_url}/o/{tenant_id}/projects/p/{project_id}/t/{thread_id}"


def annotation_queue_url(client, queue) -> str:
    """Build a UI link to an annotation queue."""
    return f"{client._host_url}/o/{queue.tenant_id}/annotation-queues/{queue.id}"


def latest_root_run(client, project_id: str, thread_id: str, retries: int = 10, delay: float = 3.0):
    """Return a thread's most recent root run (its anchor).

    LangSmith finishes indexing a thread's runs a beat after the agent does, so
    we poll until the root-run count stops growing (two equal reads) before
    trusting the newest one. Otherwise we might anchor on turn 1 before the
    final turn's run shows up — and then score/queue a trace that's missing the
    full conversation.
    """
    prev = None
    runs = []
    for _ in range(retries):
        runs = list(client.read_thread(thread_id=thread_id, project_id=project_id, order="desc"))
        if runs and len(runs) == prev:
            return runs[0]
        prev = len(runs)
        time.sleep(delay)
    return runs[0] if runs else None


def collect_threads(client, project_id: str, thread_ids: list[str], messages_by_thread: dict) -> list[dict]:
    """For each generated thread, attach its anchor run and in-memory transcript.

    The anchor run is the conversation's canonical object: a thread-level
    evaluator scores the whole conversation and pins the result there, and that
    same run is what we route for human review.
    """
    threads = []
    for tid in thread_ids:
        anchor = latest_root_run(client, project_id, tid)
        if anchor is None:
            print(f"! No runs indexed yet for thread {tid[:8]} — skipping.")
            continue
        threads.append(
            {"thread_id": tid, "anchor_run": anchor, "messages": messages_by_thread[tid]}
        )
    return threads
