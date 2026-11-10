"""Surface clickable LangSmith URLs from the eval notebooks — traces, datasets, experiments.

Keeps the link plumbing out of the notebook cells: a cell calls ``traced(agent, inputs, config)``
and gets the run's answer plus a printed trace URL, or ``experiment_url(client, results)`` after an
``evaluate()`` to print the experiment link. Every function is failure-tolerant — when tracing is
off, a key is missing, or LangSmith is unreachable, it degrades quietly (no link, no error) so the
notebook always runs standalone.

Credentials are handled entirely by the ``langsmith`` SDK (sourced from the environment); this module
only reads the ``LANGSMITH_TRACING`` boolean flag and prints workspace-scoped UI links.
"""

import os
import re

# The SDK's cb.get_run_url() returns the /r/{run}?poll=true route, which 500s ("Something went wrong")
# for some orgs. The project "peek" route renders the same trace reliably, so we rewrite the URL into
# that form. The run id IS the trace id, so peek/peeked_trace both use it.
_RUN_URL_RE = re.compile(
    r"^(?P<base>https?://[^/]+/o/[^/]+/projects/p/(?P<proj>[0-9a-fA-F-]+))/r/(?P<run>[0-9a-fA-F-]+)"
)


def _peek_url(cb) -> str:
    """Clickable trace URL. Prefer the reliable project-peek route; fall back to the raw SDK URL."""
    raw = cb.get_run_url()
    m = _RUN_URL_RE.match(raw)
    if not m:
        return raw
    proj, run = m.group("proj"), m.group("run")
    return f"{m.group('base')}?peek={run}&peek_project={proj}&peeked_trace={run}"


def traced(graph, inputs: dict, config: dict | None = None) -> dict:
    """Invoke ``graph`` and return its full result dict, printing a clickable trace URL when tracing is on.

    ``inputs`` is whatever ``.invoke`` accepts (a ``{"messages": ...}`` payload or a ``Command(resume=...)``).
    ``config`` passes through to ``.invoke`` (e.g. a ``thread_id`` for memory). When
    ``LANGSMITH_TRACING`` is not "true", it just invokes and returns — no link, no error.
    """
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        from langchain_core.tracers.context import tracing_v2_enabled

        with tracing_v2_enabled() as cb:
            result = graph.invoke(inputs, config=config)
        try:
            print("🔗 trace:", _peek_url(cb))
        except Exception:
            pass  # a missing link should never break the notebook
        return result
    return graph.invoke(inputs, config=config)


def experiment_url(client, results) -> None:
    """Print the LangSmith UI link for an ``evaluate()`` result's experiment.

    ``results`` is what ``client.evaluate(...)`` returns; its ``experiment_name`` resolves to a
    project whose ``.url`` is the workspace-scoped experiment view. ``evaluate()`` also prints a
    results URL, but this is the stable, clickable link that survives clearing cell outputs.
    """
    try:
        print("🔗 experiment:", client.read_project(project_name=results.experiment_name).url)
    except Exception:
        pass  # a missing link should never break the notebook


def dataset_url(client, name: str) -> None:
    """Print the LangSmith UI link for dataset ``name`` so it can be reviewed before an experiment runs."""
    try:
        print("📊 dataset:", client.read_dataset(dataset_name=name).url)
    except Exception:
        pass  # a missing link should never break the notebook
