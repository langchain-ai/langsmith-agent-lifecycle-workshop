"""Helpers for surfacing LangSmith links from inside the workshop notebooks.

URLs are resolved at runtime from whatever `LANGSMITH_API_KEY` /
`LANGSMITH_PROJECT` are configured, so each attendee gets links into their own
workspace rather than a hardcoded one.

Typical use in a notebook:

    from utils.langsmith_links import project_url, trace_link

    print(project_url())                      # all traces from this workshop

    with trace_link("supervisor routing"):    # link straight to one trace
        agent.invoke({"messages": [...]})

Use without a LangSmith key (Module 7). `project_url()` raises when LangSmith
cannot be reached with the configured key. A notebook that must also run
without a key calls `setup_langsmith()` instead, once, in its Setup cell:

    from utils.langsmith_links import setup_langsmith, trace_link

    LANGSMITH_AVAILABLE = setup_langsmith()   # one request at most, one printed line

    with trace_link("order status") as cb:    # prints a link, or the run tree without a key
        agent.invoke({"messages": [...]})
    root = cb.traced_runs[0]                  # the collected run, usable in every state

"No usable key" covers three states: the variable is not set, it still holds
the `.env.example` placeholder, or LangSmith rejects it. In all three,
`setup_langsmith()` returns `False`, switches trace uploads off for the process
and `trace_link` prints the run tree in the notebook instead of a link.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

import langsmith as ls
from langchain_core.tracers.context import register_configure_hook
from langchain_core.tracers.run_collector import RunCollectorCallbackHandler
from langsmith import Client
from langsmith.utils import LangSmithError, LangSmithNotFoundError

DEFAULT_PROJECT = "langsmith-agent-lifecycle-workshop"


def _project_name(project_name: str | None = None) -> str:
    return project_name or os.getenv("LANGSMITH_PROJECT", DEFAULT_PROJECT)


@lru_cache(maxsize=None)
def _project_base_url(project_name: str) -> str:
    """The project's URL in the LangSmith app (US, EU or self-hosted). Cached - one API call."""
    # This client only looks the project up; it never sends traces. Without
    # auto_batch_tracing=False it would start a background tracing thread that
    # makes a second request (GET /info) and logs a warning when that fails.
    client = Client(auto_batch_tracing=False)
    try:
        project = client.read_project(project_name=project_name)
    except LangSmithNotFoundError:
        # A fresh workspace has no project until its first trace arrives.
        project = client.create_project(project_name=project_name)
    return project.url


def project_url(project_name: str | None = None) -> str:
    """URL of the LangSmith project collecting this workshop's traces."""
    return _project_base_url(_project_name(project_name))


def trace_url(run_id, project_name: str | None = None) -> str:
    """Direct URL to a single trace."""
    return f"{project_url(project_name)}/r/{run_id}"


@lru_cache(maxsize=1)
def langsmith_status() -> tuple[bool, str]:
    """Whether LangSmith can be used, as `(available, reason)`.

    `reason` is empty when LangSmith is available. At most one API call is made,
    and the answer is cached for the process, including "not available": a
    missing or rejected key is not asked about again by every `trace_link` block.

    Only the environment variable is checked. Credentials that the LangSmith
    client could also read from a local profile file are not considered.
    """
    key = (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or "").strip()
    if not key:
        return False, "LANGSMITH_API_KEY is not set"
    if key.startswith("<"):
        # .env.example copied unchanged: a non-empty string that is not a key.
        return False, "LANGSMITH_API_KEY is still the .env.example placeholder"
    try:
        _project_base_url(_project_name())
    except LangSmithError as exc:  # auth, permission, connection, bad endpoint
        return False, f"LangSmith rejected the request ({type(exc).__name__})"
    except Exception as exc:  # noqa: BLE001 - e.g. a proxy answered with something that is not LangSmith
        return False, f"the LangSmith check failed ({type(exc).__name__})"
    return True, ""


def setup_langsmith() -> bool:
    """Call once in a notebook's Setup cell. Prints one line and returns whether LangSmith is available.

    Without a usable key, trace uploads are switched off for the whole process,
    so a `LANGSMITH_TRACING="true"` line in `.env` cannot produce upload-failure
    log lines on every agent call.
    """
    available, reason = langsmith_status()
    if available:
        print(f"📊 All traces from this workshop: {project_url()}")
    else:
        # Process-wide, and it wins over LANGSMITH_TRACING=true. Setting
        # os.environ["LANGSMITH_TRACING"] here would not work: the SDK caches
        # the first value it read.
        ls.configure(enabled=False)
        print(
            f"⏭️  LangSmith unavailable: {reason}. "
            "The labs still run; traces print here instead of linking to LangSmith."
        )
    return available


# langchain_core's collect_runs() registers its collector as not inheritable.
# For a LangGraph agent that yields disconnected fragments when tracing is off:
# the root without children, each model and tool call as its own "root", and no
# graph-node runs. An inheritable collector is passed down to every child run,
# so it holds one nested tree, with tracing on or off.
_local_collector: ContextVar[RunCollectorCallbackHandler | None] = ContextVar(
    "workshop_run_collector", default=None
)
register_configure_hook(_local_collector, inheritable=True)


@contextmanager
def collect_run_tree():
    """Like langchain_core's `collect_runs()`, but child runs nest under their parents for LangGraph agents.

    Yields the collector. After the block, `cb.traced_runs` holds the root run
    of each traced call, with `child_runs`, `inputs`, `outputs`, `tags` and
    `extra["metadata"]`. Nothing is sent anywhere by the collector itself.
    """
    cb = RunCollectorCallbackHandler()
    token = _local_collector.set(cb)
    try:
        yield cb
    finally:
        _local_collector.reset(token)


def print_run_tree(run, indent: int = 0) -> None:
    """Print one collected run and its children, the way the trace tree reads in LangSmith."""
    ms = (run.end_time - run.start_time).total_seconds() * 1000 if run.end_time else float("nan")
    detail = ""
    if run.run_type == "tool":
        detail = f"  args={str(run.inputs.get('input', run.inputs))[:70]}"
    if run.error:
        detail += "  ERROR: " + str(run.error).splitlines()[0][:80]
    print(f"{'   ' * indent}{'└─ ' if indent else ''}{run.name}  [{run.run_type}]  {ms:.0f} ms{detail}")
    for child in sorted(run.child_runs, key=lambda r: r.start_time):
        print_run_tree(child, indent + 1)


@contextmanager
def trace_link(label: str = "View trace", project_name: str | None = None):
    """Run traced code, then print a direct LangSmith link to the trace.

    When LangSmith is unavailable (see `langsmith_status`), the run tree is
    printed in the notebook instead of a link. The block yields the run
    collector, so `with trace_link("...") as cb:` gives access to the collected
    run in both cases; `with trace_link("..."):` works as before.

    Args:
        label: Text shown next to the link.
        project_name: Override the project (defaults to LANGSMITH_PROJECT).
    """
    with collect_run_tree() as cb:
        yield cb

    if not cb.traced_runs:
        print("(No LangChain run captured in this block.)")
        return

    # The root is the run that started first.
    root = min(cb.traced_runs, key=lambda run: run.start_time)
    if langsmith_status()[0]:
        try:
            print(f"\n🔗 {label}: {trace_url(root.id, project_name)}")
            return
        except Exception as exc:  # noqa: BLE001 - never break a demo over a link
            print(f"(Could not build LangSmith link: {type(exc).__name__})")
    print(f"\n🧾 {label} (local trace, not uploaded):")
    print_run_tree(root)
