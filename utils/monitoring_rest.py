"""Monitoring as code: the two LangSmith REST requests behind an online evaluator and an automation (Module 7).

The LangSmith SDK can define an evaluator and create an annotation queue, but it has no method that
*attaches* an evaluator to a tracing project or creates an automation. Both are "run rules" in the
REST API, created with `POST /api/v1/runs/rules` and listed with `GET /api/v2/runs/rules`.

This file builds those requests and can send them:

    from langsmith import Client
    from evaluators import WRONG_RETURN_WINDOW_SOURCE
    from utils.monitoring_rest import code_evaluator_rule, create_rule_once, queue_rule

    body = code_evaluator_rule(project_id=PROJECT_ID, code=WRONG_RETURN_WINDOW_SOURCE)
    print(body)                                  # building a body sends nothing
    rule = create_rule_once(Client(), body)      # sends: lists the rules first, then creates

- `code_evaluator_rule(...)` and `queue_rule(...)` return plain dictionaries: the request bodies.
  They need no key and make no request, so a notebook can always print them.
- `ls(client, method, path, ...)` sends one request. The path must be the documented one in full,
  starting with `/api/`. That is the only form the installed client turns into the documented URL
  for every shape of `LANGSMITH_ENDPOINT` (the US and EU cloud addresses, and self-hosted addresses
  that end in `/api` or `/api/v1`).
- `list_rules(client, project_id)` returns the rules of one project.
- `create_rule_once(client, body)` creates a rule unless the project already has one with the same
  `display_name`. Creating is not an upsert: without that check, running a cell twice leaves two
  rules behind.

Filters are passed through unchanged. Module 7 teaches each filter string next to a plain Python
predicate in `utils.monitoring_local.FILTERS`; the strings sent from here are those strings.

Rules are attached without backfill: no body built here has `backfill_from`, so a new rule acts on
new traces only. Module 7 scores the seeded day from the notebook instead (see
`utils.trace_upload.write_scores`).

UNVERIFIED: these requests were built from the REST reference and checked offline (the tests record
the method, the URL and the body). None was sent to LangSmith, so what a server accepts is not
known from here, in particular a rule that carries its code evaluator inline in `code_evaluators`.
Module 7 therefore keeps the sending cell switched off by default and gives the same steps in the
LangSmith UI.

Standard library only. The `client` argument is a `langsmith.Client`; this file does not import it.
"""

from __future__ import annotations

from typing import Any

RULES_CREATE_PATH = "/api/v1/runs/rules"  # POST: attach an evaluator, or create an automation
RULES_LIST_PATH = "/api/v2/runs/rules"  # GET: cursor-paginated; the v1 list endpoint is deprecated

# The filters of the two rules, in the function syntax that evaluator and automation filters use.
# They equal the strings paired with a Python predicate in `utils.monitoring_local.FILTERS`.
ROOT_RUNS_FILTER = "eq(is_root, true)"
FLAGGED_FILTER = 'and(eq(is_root, true), eq(feedback_key, "wrong_return_window"), gt(feedback_score, 0.5))'

EVALUATOR_RULE_NAME = "wrong_return_window"  # the same as the feedback key the evaluator returns, on purpose
QUEUE_RULE_NAME = "route-wrong-return-window-to-review"


def ls(client: Any, method: str, path: str, **request_arguments: Any) -> Any:
    """Send one REST request through the LangSmith client and return the decoded JSON reply (`None` if empty).

    `path` must start with `/api/`, for example `/api/v1/runs/rules`. A shorter path such as
    `/runs/rules` is refused here: the client adds no prefix of its own, so on LangSmith Cloud it
    would be sent to an address the REST reference does not document.

    `request_arguments` go to `Client.request_with_retries`: `json={...}` for a body, `params={...}`
    for a query string. The client adds the API key header, and the workspace header when
    `LANGSMITH_WORKSPACE_ID` is set (an organization-scoped key needs it).
    """
    if not path.startswith("/api/"):
        raise ValueError(f"ls(): pass the documented path in full, starting with '/api/' (got {path!r}).")
    response = client.request_with_retries(method, path, **request_arguments)
    return response.json() if response.content else None


def code_evaluator_rule(
    *,
    project_id: str,
    code: str,
    display_name: str = EVALUATOR_RULE_NAME,
    filter: str = ROOT_RUNS_FILTER,
    sampling_rate: float = 1.0,
) -> dict:
    """The body that defines a code evaluator and attaches it to one tracing project, in one request.

    - `project_id`: the tracing project's id. The REST API calls it `session_id`. In an agent-based
      workspace it is the id of the project behind the agent's environment.
    - `code`: the source text of a function named `perform_eval(run, example=None)`, for example
      `evaluators.WRONG_RETURN_WINDOW_SOURCE`.
    - `filter`: which runs are evaluated. The default selects root runs.
    - `sampling_rate`: the share of matching runs that is evaluated, from 0 to 1. The form in the
      LangSmith UI asks for the same number as a percentage from 0 to 100.
    """
    return {
        "display_name": display_name,
        "session_id": str(project_id),
        "sampling_rate": _rate(sampling_rate),
        "filter": filter,
        "code_evaluators": [{"code": code, "language": "python"}],
    }


def queue_rule(
    *,
    project_id: str,
    queue_id: str,
    display_name: str = QUEUE_RULE_NAME,
    filter: str = FLAGGED_FILTER,
    sampling_rate: float = 1.0,
) -> dict:
    """The body of an automation that adds matching runs to an annotation queue.

    The default filter selects root runs that carry the feedback `wrong_return_window` with a score
    above 0.5, so the automation picks up what the online evaluator flagged. `queue_id` is the id
    of an existing annotation queue (`Client.create_annotation_queue(...).id`).
    """
    return {
        "display_name": display_name,
        "session_id": str(project_id),
        "sampling_rate": _rate(sampling_rate),
        "filter": filter,
        "add_to_annotation_queue_id": str(queue_id),
    }


def _rate(sampling_rate: float) -> float:
    rate = float(sampling_rate)
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"sampling_rate is a share from 0 to 1 (got {sampling_rate!r}). 25% is 0.25.")
    return rate


def list_rules(client: Any, project_id: str, *, page_size: int = 100) -> list[dict]:
    """Every run rule of one tracing project: attached evaluators and automations.

    Uses `GET /api/v2/runs/rules` with `project_id` and `type=PROJECT`, and follows `next_cursor`
    until the last page. Each rule is a dictionary with `id`, `display_name`, `project_id`,
    `filter`, `sampling_rate` and more.
    """
    rules: list[dict] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"project_id": str(project_id), "type": "PROJECT", "page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        page = ls(client, "GET", RULES_LIST_PATH, params=params) or {}
        rules += page.get("items") or []
        cursor = page.get("next_cursor")
        if not cursor:
            return rules


def create_rule_once(client: Any, body: dict) -> dict | None:
    """Create the rule described by `body`, unless its project already has a rule of that name.

    Returns the stored rule as LangSmith answers it (with its `id`), or `None` when a rule with the
    same `display_name` exists and nothing was sent. Raises whatever the client raises when
    LangSmith refuses a request: the caller decides what to print (in Module 7, the same steps in
    the LangSmith UI).
    """
    existing = list_rules(client, body["session_id"])
    if any(rule.get("display_name") == body["display_name"] for rule in existing):
        return None
    return ls(client, "POST", RULES_CREATE_PATH, json=body)
