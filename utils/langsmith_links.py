"""Helpers for surfacing LangSmith links from inside the workshop notebooks.

URLs are resolved at runtime from whatever `LANGSMITH_API_KEY` /
`LANGSMITH_PROJECT` are configured, so each attendee gets links into their own
workspace rather than a hardcoded one.

Typical use in a notebook:

    from utils.langsmith_links import project_url, trace_link

    print(project_url())                      # all traces from this workshop

    with trace_link("supervisor routing"):    # link straight to one trace
        agent.invoke({"messages": [...]})
"""

import os
from contextlib import contextmanager
from functools import lru_cache

from langchain_core.tracers.context import collect_runs
from langsmith import Client
from langsmith.utils import LangSmithNotFoundError

DEFAULT_PROJECT = "langsmith-agent-lifecycle-workshop"


def _project_name(project_name: str | None = None) -> str:
    return project_name or os.getenv("LANGSMITH_PROJECT", DEFAULT_PROJECT)


@lru_cache(maxsize=None)
def _project_base_url(project_name: str) -> str:
    """The project's URL in the LangSmith app (US, EU or self-hosted). Cached - one API call."""
    client = Client()
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


@contextmanager
def trace_link(label: str = "View trace", project_name: str | None = None):
    """Run traced code, then print a direct LangSmith link to the trace.

    Args:
        label: Text shown next to the link.
        project_name: Override the project (defaults to LANGSMITH_PROJECT).
    """
    with collect_runs() as cb:
        yield

    if not cb.traced_runs:
        print("(No trace captured - is LANGSMITH_TRACING enabled?)")
        return

    try:
        # collect_runs() returns the root run alongside its children, in
        # completion order. The root is the one that started first.
        root = min(cb.traced_runs, key=lambda run: run.start_time)
        print(f"\n🔗 {label}: {trace_url(root.id, project_name)}")
    except Exception as exc:  # noqa: BLE001 - never break a demo over a link
        print(f"(Could not build LangSmith link: {exc})")
