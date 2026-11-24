"""Put the Module 7 seed into a LangSmith workspace, and send a few fresh traces (keyed helpers).

Module 7 runs without a LangSmith key: every lab reads the seed from disk. The functions in this
file are the optional other half. With a working key they write the same synthetic day into the
learner's own workspace, so the numbers computed in the notebook can also be seen in LangSmith.

    from utils.langsmith_links import setup_langsmith
    from utils.trace_seeding import load_seed
    from utils.trace_upload import resolve_destination, upload_seed, write_scores, send_live_traces

    LANGSMITH_AVAILABLE = setup_langsmith()
    DEST = resolve_destination(LANGSMITH_AVAILABLE)   # where the traces go: name, id, navigation path
    seed = load_seed()
    SEEDED = upload_seed(seed, DEST) if LANGSMITH_AVAILABLE else False

Rules every function here follows:

- **Nothing is sent without a usable key.** Each function returns at once when the destination is
  not available (`Destination.available` is `False`).
- **No function raises because LangSmith refused or could not be reached.** It prints one line that
  starts with `⏭️` and returns a value that means "nothing was written" (`False`, `0`). The notebook
  then continues in local mode. Only the type of the error is printed, never its text: an error
  message from a server can repeat the credentials that were sent.
- **No project is ever created by name and nothing is ever deleted.** A tracing project comes into
  being when its first trace arrives. Calling `create_project` on a guessed name could leave a
  stray agent in an agent-based workspace.
- **A second upload is refused.** `upload_seed` first asks LangSmith for one root run tagged
  `seed:m7` and sends no run if there is one.
- **A half-finished upload is not reported as done.** When runs tagged `seed:m7` are already
  there, `upload_seed` counts them. A complete set whose user scores are missing gets the missing
  scores; an incomplete set returns `False` with one line that says how to start clean. The same
  holds inside one process: if the runs went out and the scores did not, the next call writes
  the scores only.
- **Trace retention is not extended.** Every score is written with `extend_trace_retention=False`,
  because a score written with the SDK's default moves the whole trace to the longer, more
  expensive retention tier.

Two kinds of workspace are supported with one code path. In a project-based workspace the traces go
to the tracing project named by `M7_PROJECT` (default `techhub-deep-agent-production`). In an
agent-based workspace (traces grouped by agent and environment) set `TECHHUB_AGENT_ID` in `.env`:
the helper looks the agent up, creates it if it does not exist, and uses the tracing project that
backs the chosen environment (`TECHHUB_AGENT_ENVIRONMENT`, default `production`).

UNVERIFIED: no function in this file has been run against a live LangSmith workspace. Every request
is built with documented SDK calls and checked offline in `tests/test_trace_upload.py`, which
records the requests instead of sending them. What a server answers is not known from here: whether
back-dated traces are charted at their own time, whether the agent-based route works as
documented, how soon a new project or a new run can be read back, and how long the roughly 430
score requests of a full Section 1 take. The completeness check of `upload_seed` reads run counts
and feedback statistics back; if LangSmith shows those with a delay, a check made within seconds of
an upload can report "incomplete" for a complete set (it reads twice before it says so) or write a
second copy of a user score.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import langsmith as ls
from langsmith import Client
from langsmith import utils as ls_utils
from langsmith.uuid import uuid7_from_datetime

from utils.trace_seeding import (
    DEFAULT_PROJECT,
    SEED_TAG,
    load_seed,
    question_text,
    remap_ids,
    reply_text,
    root_runs,
    runs_by_trace,
    shift_to_now,
    trace_key,
)

AGENT_NAME = "TechHub support"  # display name given to the agent if this module has to create it
DEFAULT_ENVIRONMENT = "production"
LIVE_TAG = "live:m7"  # fresh traces sent by `send_live_traces`; the seeded day carries `seed:m7`
USER_SCORE_KEY = "user_score"  # the seeded end-user rating: 1 thumbs-up, 0 thumbs-down
QUEUE_NAME = "techhub-deep-agent-return-window-review"
QUEUE_DESCRIPTION = "Replies that the wrong_return_window evaluator flagged: a 30-day return window given for an opened or used product."
QUEUE_INSTRUCTIONS = (
    "Read the customer's message and the agent's reply. TechHub's Return Policy gives unopened electronics 30 days "
    "from delivery and opened electronics 14 days. Confirm whether the reply gives the wrong window, and correct it."
)

BATCH_SIZE = 250  # runs per `batch_ingest_runs` call
GUARD_DAYS = 7  # how far back the re-run guard looks for an earlier upload
LIVE_MINUTES = 60  # how far back `live_scores` looks for fresh traces
PROJECT_LOOKUP_ATTEMPTS = 6  # a new project may not be readable the instant its first trace was sent
FEEDBACK_ATTEMPTS = 4  # per score; the SDK waits about 1, 2 and 4 seconds between attempts when the run is not found yet
FEEDBACK_WORKERS = 8  # scores are written a few at a time, so that 260 requests do not take minutes

# The two filters this file sends. They select by tag, a key that this module itself puts on every run.
SEEDED_FILTER = f'has(tags, "{SEED_TAG}")'
LIVE_FILTER = f'has(tags, "{LIVE_TAG}")'

LOCAL_MODE = "Continuing in local mode."
# What to do after TECHHUB_AGENT_ID was added to .env, in words that fit wherever the navigation text is printed.
RERUN_THIS_STEP = "repeat this step (in a notebook, run the Setup cell again)"

_SAYS_OPENED = re.compile(r"\b(opened|used)\b", re.IGNORECASE)
_sleep = time.sleep  # replaced in tests


# ---------------------------------------------------------------------------------------------
# The client, and the two small tools the rest of the file is built on
# ---------------------------------------------------------------------------------------------


def new_client(on_error: Callable[[Exception], None] | None = None, **overrides: Any) -> Client:
    """The LangSmith client the keyed helpers of Module 7 use. Key and endpoint come from the environment.

    The settings differ from a default `Client()` in four ways, each for a reason:

    - `auto_batch_tracing=False`: requests are sent when the helper calls, not later from a
      background thread, so a helper knows whether its upload worked before it returns.
    - `omit_traced_runtime_info=True`: the uploaded runs carry exactly what the seed file says. The
      SDK would otherwise add the operating system, the Python version and every `LANGSMITH_*`
      setting of this machine to each run.
    - `hide_inputs`, `hide_outputs` and `hide_metadata` are `False` and the sampling rate is 1.0,
      whatever `LANGSMITH_HIDE_INPUTS` and similar variables say. The seed is synthetic, and the
      labs need its text in LangSmith. Module 7 Section 4 teaches those variables; trying one out
      must not silently empty the seeded day.
    - `tracing_error_callback=on_error`: `Client.batch_ingest_runs` logs a failed upload and does
      not raise. The callback is how the caller learns about it.
    """
    settings: dict[str, Any] = {
        "auto_batch_tracing": False,
        "omit_traced_runtime_info": True,
        "hide_inputs": False,
        "hide_outputs": False,
        "hide_metadata": False,
        "tracing_sampling_rate": 1.0,
        "tracing_error_callback": on_error,
    }
    return Client(**{**settings, **overrides})


@contextmanager
def _quiet_sdk_logs():
    """Silence the SDK's own log lines for the duration of one helper call.

    The SDK logs a failed request with the server's reply and a traceback. The helpers report a
    failure themselves, in one line and without the reply text.
    """
    logger = logging.getLogger("langsmith")
    previous = logger.level
    logger.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        logger.setLevel(previous)


def _await(make_coroutine: Callable[[], Any]) -> Any:
    """Run one coroutine to its end from ordinary code, in a script and in a notebook.

    `client.runs` and `client.annotation_queues` are asynchronous. A notebook already runs an event
    loop, where `asyncio.run` is not allowed, so the coroutine then runs in a thread of its own.
    Each call uses a client that no other event loop has used (see `_query_root_runs`): an HTTP
    connection opened inside one event loop cannot be reused from another.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(make_coroutine())
    outcome: dict[str, Any] = {}

    def work() -> None:
        try:
            outcome["value"] = asyncio.run(make_coroutine())
        except BaseException as exc:  # noqa: BLE001 - handed to the calling thread below
            outcome["error"] = exc

    thread = threading.Thread(target=work, name="module7-langsmith-query", daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def _query_root_runs(project_id: str, tag_filter: str, selects: list[str], *, since: datetime, page_size: int = 100, limit: int | None = None) -> list:
    """Root runs of one project that match `tag_filter` and started after `since`.

    `client.runs.query` looks back one day unless `min_start_time` is given, takes project ids (not
    names), and returns only the fields named in `selects`.
    """
    client = new_client()  # a client of its own: see `_await`

    async def fetch() -> list:
        found = []
        async for run in client.runs.query(
            project_ids=[str(project_id)],
            is_root=True,
            filter=tag_filter,
            min_start_time=since,
            page_size=page_size,
            selects=selects,
        ):
            found.append(run)
            if limit is not None and len(found) >= limit:
                break
        return found

    return _await(fetch)


def _days_ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _as_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


# ---------------------------------------------------------------------------------------------
# Where the traces go
# ---------------------------------------------------------------------------------------------


@dataclass
class Destination:
    """Where Module 7 writes its traces, and how to find them in LangSmith.

    - `available`: whether LangSmith can be used. When `False`, every keyed helper returns at once.
    - `project_name`: the tracing project the runs are sent to. In an agent-based workspace this
      is the project that backs the chosen environment of the agent.
    - `project_id`: that project's id, which scores, queries and rules need. `None` until the
      project exists, which in a project-based workspace is after the first upload.
    - `where`: the path to the traces in the LangSmith UI, for example
      `Tracing > project 'techhub-deep-agent-production'`.
    - `navigation`: the same as one full sentence, for printing after an upload. A script that
      wants to name the command to run again calls `how_to_find(rerun="...")` instead.
    - `url`: a link to the project, when LangSmith returned one.
    - `uploaded`: filled by `upload_seed`. Trace key (such as `t-0042`) to the id, trace id and
      start time of the uploaded root run. Run ids are new on every upload, so this is how a later
      cell finds "the same trace" in LangSmith.
    - `scored`: the feedback keys `write_scores` has written in this process, so that running the
      cell a second time does not write every score twice.
    - `pending_scores`: user scores of this process's upload that are not written yet. Not empty
      only after an upload whose runs were sent and whose scores failed; the next `upload_seed`
      call writes these and sends no run.
    - `partial`: `True` after an upload in this process that stopped between two batches of runs,
      so the project holds some of the seeded traces and not all.
    - `queues_filled`, `queues_open`: review queues `send_to_queue` filled in this process, and
      queues it created and could not fill (name to queue id), which the next call fills.
    """

    available: bool
    project_name: str
    project_id: str | None = None
    where: str = ""
    agent_id: str | None = None
    agent_name: str | None = None
    environment: str | None = None
    url: str | None = None
    uploaded: dict[str, dict] = field(default_factory=dict, repr=False)
    scored: set[str] = field(default_factory=set, repr=False)
    pending_scores: list[dict] = field(default_factory=list, repr=False)
    partial: bool = False
    queues_filled: set[str] = field(default_factory=set, repr=False)
    queues_open: dict[str, str] = field(default_factory=dict, repr=False)

    def refresh(self) -> "Destination":
        """Ask LangSmith for the project id and link again. Returns the same object and never raises.

        Call it after the first upload: before that, a project-based workspace has no project of
        this name and `project_id` is `None`. Without a usable key nothing is asked.
        """
        if not self.available:
            return self
        try:
            with _quiet_sdk_logs():
                self._read_project(new_client())
        except Exception:  # noqa: BLE001 - the id stays as it was; the keyed helpers report their own failures
            pass
        return self

    def _read_project(self, client: Client) -> None:
        try:
            project = client.read_project(project_name=self.project_name)
        except ls_utils.LangSmithNotFoundError:
            return  # no trace has arrived yet
        if not (self.agent_id and self.project_id):  # an id that the agent's environment gave is kept
            self.project_id = str(project.id)
        try:
            self.url = project.url
        except Exception:  # noqa: BLE001 - the link is a convenience; the navigation path is always printed with it
            self.url = None

    def how_to_find(self, rerun: str = RERUN_THIS_STEP) -> str:
        """How to reach the traces in LangSmith, with the time range to set.

        In a project-based destination the text ends with what to do if the workspace turns out to
        be agent-based: set `TECHHUB_AGENT_ID` and `rerun`. `rerun` is the instruction that fits
        the caller, without a full stop: the default fits a notebook and a script alike; a script
        passes the command to run again.
        """
        time_range = "Set the time range to at least the last 2 days."
        if self.agent_id:
            return (
                f"In LangSmith, open Tracing, select the agent '{self.agent_name or self.agent_id}' in the agent switcher "
                f"in the top bar, and set the environment control to {(self.environment or DEFAULT_ENVIRONMENT).capitalize()}. {time_range}"
            )
        return (
            f"In LangSmith, open Tracing, then the tracing project '{self.project_name}'. {time_range} "
            "If the control at the top left shows your workspace name instead of the LangSmith logo, your workspace is "
            f"agent-based: set TECHHUB_AGENT_ID in .env and {rerun}."
        )

    @property
    def navigation(self) -> str:
        """`how_to_find()` with its default wording, as one attribute for printing."""
        return self.how_to_find()


_last_destination: Destination | None = None


def _forget_agent_addressing() -> None:
    """Remove `LANGSMITH_AGENT_ID` and `LANGSMITH_AGENT_ENVIRONMENT` from this process.

    Module 7 sends its traces to a project by name in both kinds of workspace. If these two
    variables are set next to a project name, the SDK skips tracing for every call that names no
    destination in code. The SDK remembers each environment variable it has read, so its memory is
    cleared as well.
    """
    removed = [name for name in ("LANGSMITH_AGENT_ID", "LANGSMITH_AGENT_ENVIRONMENT") if os.environ.pop(name, None) is not None]
    if removed and hasattr(ls_utils.get_env_var, "cache_clear"):
        ls_utils.get_env_var.cache_clear()


def resolve_destination(available: bool, project_name: str | None = None) -> Destination:
    """Decide where Module 7 writes its traces. Call it once, in the Setup cell.

    `available` is the result of `setup_langsmith()`. Without a usable key no request is made and
    nothing is printed. With one, the function prints `Seeded traffic goes to: <where>`.

    - **Project-based workspace** (no `TECHHUB_AGENT_ID`): the project is `project_name`, or the
      environment variable `M7_PROJECT`, or `techhub-deep-agent-production`. One request looks its
      id up; the project is not created here.
    - **Agent-based workspace** (`TECHHUB_AGENT_ID` set): the agent is retrieved, and created as an
      external agent named "TechHub support" if LangSmith answers that it does not exist. The
      destination is the tracing project behind the environment `TECHHUB_AGENT_ENVIRONMENT`
      (default `production`). UNVERIFIED against a live workspace: if any step fails, one line is
      printed and the returned destination is not available, so the notebook runs in local mode.

    The function also removes `LANGSMITH_AGENT_ID` and `LANGSMITH_AGENT_ENVIRONMENT` from the
    process (see `_forget_agent_addressing`).
    """
    global _last_destination
    _forget_agent_addressing()
    name = project_name or os.getenv("M7_PROJECT") or DEFAULT_PROJECT
    agent_id = (os.getenv("TECHHUB_AGENT_ID") or "").strip()
    environment = (os.getenv("TECHHUB_AGENT_ENVIRONMENT") or DEFAULT_ENVIRONMENT).strip().lower()

    if agent_id and not project_name:
        destination = Destination(
            available=available,
            project_name=name,
            agent_id=agent_id,
            agent_name=AGENT_NAME,
            environment=environment,
            where=f"Tracing > agent '{AGENT_NAME}' > environment {environment.capitalize()}",
        )
        if available:
            try:
                with _quiet_sdk_logs():
                    _resolve_agent(destination, new_client())
            except Exception as exc:  # noqa: BLE001 - the agent-based route is unverified; any failure means local mode
                destination.available = False
                print(f"⏭️  Could not use the agent '{agent_id}' as the destination ({type(exc).__name__}). {LOCAL_MODE}")
    else:
        destination = Destination(available=available, project_name=name, where=f"Tracing > project '{name}'")
        destination.refresh()

    if destination.available:
        print(f"Seeded traffic goes to: {destination.where}")
    _last_destination = destination
    return destination


def _resolve_agent(destination: Destination, client: Client) -> None:
    """Fill `destination` from the agent's environment: project name, project id, display name."""
    try:
        agent = client.agents.retrieve(destination.agent_id)
    except ls.NotFoundError:
        # A tracing key cannot create an agent, and neither can a role without the permission to
        # create projects. Both end in the caller's `except`: local mode.
        agent = client.agents.create(id=destination.agent_id, name=AGENT_NAME, source_type="EXTERNAL")
        if not agent.environments:
            agent = client.agents.retrieve(destination.agent_id)
    wanted = (destination.environment or DEFAULT_ENVIRONMENT).upper()
    chosen = next((env for env in agent.environments or [] if env.environment == wanted), None)
    if chosen is None:
        raise LookupError(f"agent {destination.agent_id!r} has no environment {wanted}")
    destination.project_name = chosen.tracer_session_name
    destination.project_id = str(chosen.tracer_session_id)
    destination.agent_name = agent.name or destination.agent_id
    destination.where = f"Tracing > agent '{destination.agent_name}' > environment {wanted.capitalize()}"
    try:
        destination._read_project(client)  # for the link; the id is already known
    except Exception:  # noqa: BLE001 - a link is optional
        pass


def _destination(dest: Destination | None) -> Destination:
    """The destination a helper was given, or the one `resolve_destination` returned last."""
    if dest is not None:
        return dest
    if _last_destination is None:
        raise RuntimeError("call resolve_destination(...) first, or pass dest=")
    return _last_destination


# ---------------------------------------------------------------------------------------------
# Uploading runs and scores
# ---------------------------------------------------------------------------------------------


def _create_payload(run: dict, project_name: str) -> dict:
    """What is sent when a run starts. `session_name` is the tracing project's name."""
    payload = {key: run[key] for key in ("id", "trace_id", "parent_run_id", "dotted_order", "name", "run_type", "start_time", "inputs", "extra", "tags")}
    payload["session_name"] = project_name
    return payload


def _update_payload(run: dict) -> dict:
    """What is sent when a run ends: its outputs, its error and its end time."""
    return {key: run[key] for key in ("id", "trace_id", "parent_run_id", "dotted_order", "end_time", "outputs", "error")}


def _chunks(items: list, size: int = BATCH_SIZE) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _send_runs(client: Client, errors: list[Exception], runs: list[dict], project_name: str, accepted: list[int] | None = None) -> None:
    """Send `runs` as create batches followed by update batches. Raises if any batch failed.

    Two steps, because that is what a live LangChain tracer does (a run is posted when it starts
    and patched when it ends); the Academy seeding scripts found that cost and token charts depend
    on it. Runs are ordered parents first. `accepted` receives the size of every batch that went
    through, so a caller can tell "nothing was sent" from "it stopped part-way".
    """
    ordered = sorted(runs, key=lambda run: run["dotted_order"])
    for chunk in _chunks([_create_payload(run, project_name) for run in ordered]):
        client.batch_ingest_runs(create=chunk)
        _raise_first(errors)
        if accepted is not None:
            accepted.append(len(chunk))
    for chunk in _chunks([_update_payload(run) for run in ordered]):
        client.batch_ingest_runs(update=chunk)
        _raise_first(errors)
        if accepted is not None:
            accepted.append(len(chunk))
    client.flush()
    _raise_first(errors)


def _raise_first(errors: list[Exception]) -> None:
    if errors:
        raise errors[0]


def _write_feedback(client: Client, rows: list[dict], project_id: str, written: list[dict] | None = None) -> None:
    """Write one score per row with `Client.create_feedback`. Raises the first failure.

    Each row has `run_id`, `trace_id`, `key`, `score` and `start_time`. `session_id` (the project
    id) is required for a score on a run, and `extend_trace_retention=False` keeps the trace on
    the base retention tier. The first score is written alone, so that a wrong project id or a
    rejected key fails once and not eight times at the same moment. `written` receives every row
    whose score was accepted, so that a caller can write only the rest after a failure.
    """
    failed: list[Exception] = []

    def write(row: dict) -> None:
        if failed:
            return
        try:
            client.create_feedback(
                run_id=row["run_id"],
                trace_id=row["trace_id"],
                key=row["key"],
                score=row["score"],
                session_id=project_id,
                start_time=_as_datetime(row["start_time"]),
                extend_trace_retention=False,
                stop_after_attempt=FEEDBACK_ATTEMPTS,
            )
        except Exception as exc:  # noqa: BLE001 - collected, and raised once all workers have stopped
            failed.append(exc)
        else:
            if written is not None:
                written.append(row)

    if rows:
        write(rows[0])
    if len(rows) > 1 and not failed:
        with ThreadPoolExecutor(max_workers=FEEDBACK_WORKERS, thread_name_prefix="module7-feedback") as pool:
            list(pool.map(write, rows[1:]))
    _raise_first(failed)


def upload_plan(seed: dict) -> dict:
    """What `upload_seed` would send for this seed, as counts. Makes no request."""
    runs = len(seed["runs"])
    batches = len(_chunks(list(range(runs))))
    return {
        "traces": len(root_runs(seed)),
        "runs": runs,
        "create_batches": batches,
        "update_batches": batches,
        "batch_size": BATCH_SIZE,
        "feedback_calls": len(seed["feedback"]),
    }


def _print_plan(seed: dict, dest: Destination) -> None:
    plan = upload_plan(seed)
    print("Dry run: nothing is sent.")
    print(f"  destination:    {dest.where}")
    print(f"  traces:         {plan['traces']} ({plan['runs']:,} runs)")
    print(
        f"  batch calls:    {plan['create_batches'] + plan['update_batches']} "
        f"({plan['create_batches']} create, then {plan['update_batches']} update; at most {plan['batch_size']} runs each)"
    )
    print(f"  feedback calls: {plan['feedback_calls']} (key {USER_SCORE_KEY}, one per rated conversation)")


def _project_id_after_upload(client: Client, dest: Destination) -> str:
    """The project id, read after the first runs were sent. Waits a little for a brand-new project."""
    for attempt in range(PROJECT_LOOKUP_ATTEMPTS):
        dest._read_project(client)
        if dest.project_id:
            return dest.project_id
        if attempt + 1 < PROJECT_LOOKUP_ATTEMPTS:
            _sleep(1.0)
    raise LookupError(f"project {dest.project_name!r} cannot be read yet")


def _write_pending_scores(client: Client, dest: Destination, project_id: str) -> int:
    """Write `dest.pending_scores` and take every accepted row off that list, also when a later row fails. Returns how many were written."""
    written: list[dict] = []
    try:
        _write_feedback(client, dest.pending_scores, project_id, written)
    finally:
        done = {id(row) for row in written}
        dest.pending_scores = [row for row in dest.pending_scores if id(row) not in done]
    return len(written)


def _seeded_roots(dest: Destination, *, with_stats: bool = False) -> tuple[dict[str, dict], dict[str, dict]]:
    """The uploaded root runs tagged `seed:m7`, newest per trace key, read back from LangSmith.

    Returns `(roots, stats)`: trace key to `{"run_id", "trace_id", "start_time"}`, and trace key to
    that run's feedback statistics (feedback key to counts; empty unless `with_stats`).
    """
    selects = ["ID", "TRACE_ID", "START_TIME", "METADATA", *(["FEEDBACK_STATS"] if with_stats else [])]
    found = _query_root_runs(dest.project_id, SEEDED_FILTER, selects, since=_days_ago(GUARD_DAYS))
    newest: dict[str, dict] = {}
    stats: dict[str, dict] = {}
    for run in found:
        key = (run.metadata or {}).get("seed_trace_key")
        if not key or not run.id or not run.start_time:
            continue
        if key not in newest or run.start_time > newest[key]["start_time"]:
            newest[key] = {"run_id": str(run.id), "trace_id": str(run.trace_id or run.id), "start_time": run.start_time}
            stats[key] = (run.feedback_stats or {}) if with_stats else {}
    return newest, stats


def _incomplete_line(dest: Destination, have: int | None, expected: int) -> str:
    """The one line for a project that holds some of the seeded traces and not all, with the way out."""
    holds = f"holds {have} of the {expected} seeded traces" if have is not None else f"holds only some of the {expected} seeded traces"
    if dest.agent_id:
        clean = "choose another environment of the agent with TECHHUB_AGENT_ENVIRONMENT in .env"
    else:
        clean = "set M7_PROJECT in .env to a project name that does not exist yet"
    return (
        f"⏭️  Incomplete upload: {dest.where} {holds}, because an earlier upload stopped part-way. Nothing was sent. "
        f"If that upload ran less than a minute ago, wait and run this again. Otherwise, to start clean, {clean}, "
        f"then run the setup step and the upload again. {LOCAL_MODE}"
    )


def _complete_earlier_upload(seed: dict, dest: Destination, client: Client) -> bool:
    """An earlier upload is in the project: is it whole? Writes user scores that are missing. Sends no run.

    Called by `upload_seed` after its guard found a root run tagged `seed:m7`. All seeded root
    runs are read back with their feedback statistics. If a trace of the seed is missing, the
    read is repeated once after 3 seconds (a run may not be readable the moment it was sent);
    if one is still missing, the upload was cut short: one line says so and how to start clean,
    and the function returns `False`. If every trace is there, each user score of the seed that
    its run does not carry yet is written, and the function returns `True`.
    """
    expected = [trace_key(run) for run in root_runs(seed)]
    roots, stats = _seeded_roots(dest, with_stats=True)
    if any(key not in roots for key in expected):
        _sleep(3.0)
        roots, stats = _seeded_roots(dest, with_stats=True)
    have = sum(1 for key in expected if key in roots)
    if have < len(expected):
        print(_incomplete_line(dest, have, len(expected)))
        return False
    dest.uploaded = {key: roots[key] for key in expected}
    dest.pending_scores = [
        {**roots[row["trace_key"]], "key": row["key"], "score": row["score"]}
        for row in seed["feedback"]
        if row["key"] not in stats[row["trace_key"]]
    ]
    already = f"Already uploaded: {dest.where} has traces tagged {SEED_TAG} from the last {GUARD_DAYS} days."
    if not dest.pending_scores:
        print(f"{already} Nothing was sent.")
        return True
    written = _write_pending_scores(client, dest, dest.project_id)
    print(f"{already} No run was sent; {written} user scores were missing and have been written.")
    return True


def upload_seed(seed: dict, dest: Destination, *, dry_run: bool = False) -> bool:
    """Upload the seeded day to LangSmith. Returns whether the workspace now holds it (`SEEDED`).

    Steps, in order:

    1. Stop if an upload is already there: ask for one root run tagged `seed:m7` that started in
       the last 7 days. If there is one, no run is sent. The function then checks that the earlier
       upload is whole (`_complete_earlier_upload`): it returns `True` for a complete set, after
       writing any user score that is missing, and `False` with one line for an incomplete set.
       When this process has already uploaded to this destination, it returns `True` without a
       request.
    2. Shift every timestamp so that the newest trace started 5 minutes ago.
    3. Give every run a new id, a UUID version 7 built from its own start time, so that ids and
       times agree and a later upload cannot collide with this one. A root run's id is its trace id.
    4. Append a short suffix to every `thread_id`, so that conversations of two uploads never join.
    5. Send the runs with `Client.batch_ingest_runs(create=...)`, then `(update=...)`, 250 at a time.
    6. Write the 170 user scores with `Client.create_feedback(...)`.

    With `dry_run=True` the function only prints what it would send and returns `False`.

    Any failure prints `⏭️  Upload failed (<error type>). Continuing in local mode.` and returns
    `False`; nothing is raised, and the function never deletes anything. What a failure leaves
    behind decides what the next call does:

    - Nothing was accepted: the next call starts again from step 1.
    - All runs were sent and writing the scores failed: the runs stay. Call `upload_seed` again
      and it writes the scores that are still missing, sends no run, and returns `True`.
    - It stopped between two batches of runs: the project holds some traces and not all. The next
      call sends nothing, says so in one line with the way to start clean, and returns `False`.
    """
    if dry_run:
        _print_plan(seed, dest)
        return False
    if not dest.available:
        print("⏭️  Skipped: LangSmith is not available. Every cell below analyses the same traces locally.")
        return False
    if dest.pending_scores:
        # The runs of this session's upload are in the project and some user scores are not. Send those only.
        try:
            with _quiet_sdk_logs():
                client = new_client()
                written = _write_pending_scores(client, dest, dest.project_id or _project_id_after_upload(client, dest))
        except Exception as exc:  # noqa: BLE001
            print(f"⏭️  Upload failed ({type(exc).__name__}). {LOCAL_MODE}")
            return False
        print(f"The {len(dest.uploaded)} traces were already sent in this session. Wrote the {written} user scores that were missing. 📊 {dest.url or dest.where}")
        return True
    if dest.uploaded:
        # LangSmith may not show a run in a query the second it was sent, so the guard below could miss it.
        print(f"Already uploaded in this session: {len(dest.uploaded)} traces are in {dest.where}. Nothing was sent.")
        return True
    if dest.partial:
        print(_incomplete_line(dest, None, len(root_runs(seed))))
        return False
    accepted: list[int] = []
    try:
        with _quiet_sdk_logs():
            errors: list[Exception] = []
            client = new_client(errors.append)
            dest._read_project(client)
            if dest.project_id and _query_root_runs(dest.project_id, SEEDED_FILTER, ["ID"], since=_days_ago(GUARD_DAYS), page_size=1, limit=1):
                return _complete_earlier_upload(seed, dest, client)
            upload = remap_ids(shift_to_now(seed), new_id=uuid7_from_datetime, thread_suffix=f"-{secrets.token_hex(3)}")
            rows = [{"run_id": row["run_id"], "trace_id": row["trace_id"], "key": row["key"], "score": row["score"], "start_time": row["run_start_time"]} for row in upload["feedback"]]
            _send_runs(client, errors, upload["runs"], dest.project_name, accepted)
            # From here on the runs are in the project. If a later step fails, the next call writes the scores and sends no run.
            dest.uploaded = {trace_key(run): {"run_id": run["id"], "trace_id": run["trace_id"], "start_time": _as_datetime(run["start_time"])} for run in root_runs(upload)}
            dest.pending_scores = rows
            _write_pending_scores(client, dest, _project_id_after_upload(client, dest))
    except Exception as exc:  # noqa: BLE001 - a failed upload never stops the lab
        if accepted and not dest.uploaded:
            dest.partial = True  # some batches of runs went through and a later one did not
        print(f"⏭️  Upload failed ({type(exc).__name__}). {LOCAL_MODE}")
        return False
    print(f"Uploaded {len(dest.uploaded)} traces and {len(rows)} user scores. 📊 {dest.url or dest.where}")
    print(f"   Find them under: {dest.where} (time range: at least the last 2 days)")
    return True


def uploaded_roots(dest: Destination | None = None) -> dict[str, dict]:
    """Trace key to `{"run_id", "trace_id", "start_time"}` for the uploaded root runs of the seed.

    Straight from memory if `upload_seed` ran in this process. Otherwise (a restarted kernel, or
    an upload made with the command line) the root runs tagged `seed:m7` are read back from
    LangSmith, and each one is matched to its trace key through the metadata `seed_trace_key`.
    Raises if LangSmith cannot be asked; the helpers that call this one turn that into one line.
    """
    dest = _destination(dest)
    if dest.uploaded:
        return dest.uploaded
    if not dest.available:
        return {}
    if not dest.project_id:
        dest._read_project(new_client())
    if not dest.project_id:
        return {}
    newest, _ = _seeded_roots(dest)
    dest.uploaded = newest
    return newest


def write_scores(seed: dict, dest: Destination, perform_eval: Callable[..., dict]) -> dict:
    """Run a code evaluator locally over the seed's root runs and log each result to LangSmith.

    `perform_eval(run, example=None)` returns `{feedback key: score}`, the contract of a LangSmith
    code evaluator. Each result is written to the matching uploaded run with
    `Client.create_feedback(run_id=..., trace_id=..., key=..., score=..., session_id=<project id>,
    start_time=..., extend_trace_retention=False)`. This is the documented replacement for the
    deprecated `evaluate_run()`: run the evaluator yourself and log the result as feedback.

    Returns `{"written": <number of scores>, "flagged": {<key>: <number of runs scored true>}}` and
    prints one line, for example `Wrote 260 scores. 11 runs carry wrong_return_window = 1.`
    On any failure it prints one `⏭️` line and returns `{"written": 0, "flagged": {}}`.

    Calling it a second time in the same process for the same feedback key writes nothing: the
    scores are already there, and a second copy would only double the count on every run. After a
    kernel restart the function cannot know that, and writes them again.

    An error raised by `perform_eval` itself is not caught: it is a bug in the evaluator, and the
    traceback is what its author needs.
    """
    nothing = {"written": 0, "flagged": {}}
    if not dest.available:
        print("⏭️  Skipped: LangSmith is not available.")
        return nothing
    results = [(trace_key(run), perform_eval(run) or {}) for run in root_runs(seed)]
    try:
        with _quiet_sdk_logs():
            roots = uploaded_roots(dest)
            if not roots or not dest.project_id:
                print(f"⏭️  Skipped: no uploaded traces tagged {SEED_TAG} were found. Run the upload cell first.")
                return nothing
            rows, flagged = [], {}
            for key_of_trace, result in results:
                target = roots.get(key_of_trace)
                if target is None:
                    continue
                for key, score in result.items():
                    value = int(score) if isinstance(score, bool) else score
                    rows.append({**target, "key": key, "score": value})
                    flagged[key] = flagged.get(key, 0) + (1 if value else 0)
            if rows and set(flagged) <= dest.scored:
                print(f"Already written in this session: scores for {', '.join(sorted(flagged))}. Nothing was sent.")
                return {"written": 0, "flagged": flagged}
            _write_feedback(new_client(), rows, dest.project_id)
            dest.scored |= set(flagged)
    except Exception as exc:  # noqa: BLE001
        print(f"⏭️  Writing scores failed ({type(exc).__name__}). {LOCAL_MODE}")
        return nothing
    carried = "; ".join(f"{count} runs carry {key} = 1" for key, count in flagged.items())
    print(f"Wrote {len(rows)} scores. {carried}." if carried else f"Wrote {len(rows)} scores.")
    return {"written": len(rows), "flagged": flagged}


# ---------------------------------------------------------------------------------------------
# Fresh traces, dated now
# ---------------------------------------------------------------------------------------------


def _first_turn_only(run: dict) -> bool:
    """True if the root run is the first turn of its conversation, so the trace stands on its own."""
    messages = (run.get("outputs") or {}).get("messages") or []
    return sum(1 for message in messages if message.get("type") == "human") <= 1


def _live_templates(seed: dict, kind: str, n: int) -> tuple[list[str], int]:
    """The trace keys of the seed traces to replay, and how many of them give the wrong return window."""
    roots = sorted(root_runs(seed), key=trace_key)
    newest_version = max(run["extra"]["metadata"]["app_version"] for run in roots)
    current = [run for run in roots if run["extra"]["metadata"]["app_version"] == newest_version]
    if kind == "quality":
        about_return = [run for run in current if "30 days" in reply_text(run) and _first_turn_only(run)]
        wrong = [trace_key(run) for run in about_return if _SAYS_OPENED.search(question_text(run))]
        right = [trace_key(run) for run in about_return if not _SAYS_OPENED.search(question_text(run))]
        if not wrong or not right:
            raise LookupError("the seed has no return-window traces to replay")
        n_wrong = n // 2
        keys: list[str] = []
        for i in range(n - n_wrong):  # alternate: wrong, right, wrong, right ...
            if i < n_wrong:
                keys.append(wrong[i % len(wrong)])
            keys.append(right[i % len(right)])
        return keys, n_wrong
    if kind == "errors":
        failed = [trace_key(run) for run in current if run["error"] and run["error"].startswith("OrderServiceUnavailable")]
        if not failed:
            raise LookupError("the seed has no errored order-service traces to replay")
        return [failed[i % len(failed)] for i in range(n)], 0
    raise ValueError(f"send_live_traces: unknown kind {kind!r}. Use 'quality' or 'errors'.")


def build_live_traces(kind: str, n: int, now: datetime | None = None) -> tuple[list[dict], int]:
    """Build `n` fresh traces dated now, without sending them. Returns `(runs, wrong_answers)`.

    The traces are copies of seed traces of the newest release, re-dated and re-keyed. No model
    is called. `kind="quality"` gives return-window questions, half of them (rounded down) answered
    with the wrong window; `kind="errors"` gives root runs that failed in `get_order_status`.

    Every run gets a new id, the tag `live:m7` instead of `seed:m7`, a new `thread_id`, and a
    `seed_trace_key` such as `lq-01` (quality) or `le-01` (errors). The last trace ends 2 seconds
    before `now` and the others a few seconds apart before it, so every root run started within
    the last minute.
    """
    seed = load_seed(shift_to_now=False)
    keys, wrong = _live_templates(seed, kind, n)
    now = now or datetime.now(timezone.utc)
    by_key = runs_by_trace(seed)
    step = min(8.0, 40.0 / max(1, n - 1))
    batch = secrets.token_hex(3)
    runs: list[dict] = []
    for i, key in enumerate(keys):
        members = sorted(by_key[key], key=lambda run: run["start_time"])
        root = members[0]
        duration = (_as_datetime(root["end_time"]) - _as_datetime(root["start_time"])).total_seconds()
        age = 2.0 + (n - 1 - i) * step + duration  # how long ago this trace's root run starts
        one = {"meta": {"clock": {"shifted_by_seconds": 0.0}}, "runs": members, "feedback": []}
        one = shift_to_now(one, now=now, newest_age=timedelta(seconds=age))
        live_key = f"l{kind[0]}-{i + 1:02d}"
        for run in one["runs"]:
            metadata = {**run["extra"]["metadata"], "thread_id": f"thread-m7-live-{batch}-{i + 1:02d}", "seed_trace_key": live_key}
            run["extra"] = {**run["extra"], "metadata": metadata}
            run["tags"] = [LIVE_TAG if tag == SEED_TAG else tag for tag in run["tags"]]
        runs += remap_ids(one, new_id=uuid7_from_datetime)["runs"]
    return runs, wrong


def send_live_traces(kind: str, n: int, dest: Destination | None = None) -> int:
    """Send `n` fresh traces dated now to the destination. Returns how many were sent (0 on failure).

    Use it after attaching an online evaluator or creating an alert in the LangSmith UI: those act
    on new traffic, and the seeded day is hours old.

    - `send_live_traces("quality", 4)`: 4 return-window turns, 2 of them with the wrong window.
    - `send_live_traces("errors", 5)`: 5 errored root runs, enough to cross an error-count
      threshold of 3 inside one 5-minute window.

    `dest` defaults to the destination `resolve_destination` returned last. No model is called.
    When LangSmith scores the new traces, and when an alert fires, is not documented.
    """
    # A wrong `kind`, or no destination at all, is a mistake in the calling code: both raise here.
    runs, wrong = build_live_traces(kind, n)
    dest = _destination(dest)
    if not dest.available:
        print("⏭️  Skipped: LangSmith is not available.")
        return 0
    try:
        with _quiet_sdk_logs():
            errors: list[Exception] = []
            _send_runs(new_client(errors.append), errors, runs, dest.project_name)
    except Exception as exc:  # noqa: BLE001
        print(f"⏭️  Sending fresh traces failed ({type(exc).__name__}). {LOCAL_MODE}")
        return 0
    if kind == "quality":
        print(f"Sent {n} fresh traces ({wrong} give the wrong window). Refresh the feedback column.")
    else:
        print(f"Sent {n} errored runs dated now. When the alert fires is not documented.")
    return n


def live_scores(dest: Destination | None = None, key: str = "wrong_return_window", minutes: int = LIVE_MINUTES) -> tuple[int, int]:
    """How many fresh traces already carry the feedback `key`, as `(scored, sent)`. Does not wait.

    Asks for the root runs tagged `live:m7` that started in the last `minutes` minutes, with their
    feedback statistics. The time from a trace to its evaluator score is not documented, so 0 is a
    normal answer right after sending: carry on and call this again later.
    """
    dest = _destination(dest)
    if not dest.available:
        print("⏭️  Skipped: LangSmith is not available.")
        return 0, 0
    try:
        with _quiet_sdk_logs():
            if not dest.project_id:
                dest._read_project(new_client())
            if not dest.project_id:
                print("⏭️  Skipped: the project does not exist yet. Run the upload cell first.")
                return 0, 0
            found = _query_root_runs(dest.project_id, LIVE_FILTER, ["ID", "FEEDBACK_STATS"], since=_days_ago(minutes / 1440))
    except Exception as exc:  # noqa: BLE001
        print(f"⏭️  Reading the scores back failed ({type(exc).__name__}). {LOCAL_MODE}")
        return 0, 0
    scored = sum(1 for run in found if key in (run.feedback_stats or {}))
    print(
        f"{scored} of {len(found)} scored so far ({key} on the fresh traces of the last {minutes} minutes). "
        "The time from trace to score is not documented; if it is 0, carry on and re-run this cell later."
    )
    return scored, len(found)


# ---------------------------------------------------------------------------------------------
# Routing flagged runs to an annotation queue
# ---------------------------------------------------------------------------------------------


def send_to_queue(
    dest: Destination,
    trace_keys: list[str],
    *,
    name: str = QUEUE_NAME,
    description: str = QUEUE_DESCRIPTION,
    rubric_instructions: str = QUEUE_INSTRUCTIONS,
) -> int:
    """Create the review queue and add the uploaded root runs of `trace_keys`. Returns the number of items sent.

    If a queue of this name already exists, nothing is added and 0 is returned, so running the cell
    twice does not fill the queue twice. Otherwise the queue is created with
    `Client.create_annotation_queue(name=..., description=..., rubric_instructions=...)` and the runs
    are added with `client.annotation_queues.items.create(queue_id, items=[{"item_type": "RUN",
    "run_id": ..., "project_id": ..., "start_time": ...}], extend_trace_retention=False)`.

    One exception to "nothing is added": a queue that this process created and then could not fill
    (the second request failed). It is remembered in `dest.queues_open`, and the next call adds
    the items to it. After a restart the function cannot know whether an existing queue was
    filled, so it adds nothing and its line says how to recover if the queue is empty.
    """
    if not dest.available:
        print("⏭️  Skipped: LangSmith is not available.")
        return 0
    try:
        with _quiet_sdk_logs():
            roots = uploaded_roots(dest)
            chosen = [roots[key] for key in trace_keys if key in roots]
            if not chosen or not dest.project_id:
                print(f"⏭️  Skipped: no uploaded traces tagged {SEED_TAG} were found. Run the upload cell first.")
                return 0
            client = new_client()
            existing = next(iter(client.list_annotation_queues(name=name)), None)
            if existing is not None and name not in dest.queues_open:
                line = f"Queue {name} already exists: nothing was added. Open Annotation Queues to see it."
                if name not in dest.queues_filled:
                    # Not filled by this process: an earlier process may have created it and stopped before the items went in.
                    line += " If it is empty, an earlier run stopped before filling it: delete the queue there and run this again, or pass another name=."
                print(line)
                return 0
            if existing is None:
                existing = client.create_annotation_queue(name=name, description=description, rubric_instructions=rubric_instructions)
                dest.queues_open[name] = str(existing.id)  # created and still empty: a later call may fill it
            items = [{"item_type": "RUN", "run_id": item["run_id"], "project_id": dest.project_id, "start_time": item["start_time"]} for item in chosen]
            adder = new_client()  # a client of its own for the one asynchronous call: see `_await`
            _await(lambda: adder.annotation_queues.items.create(str(existing.id), items=items, extend_trace_retention=False))
            dest.queues_open.pop(name, None)
            dest.queues_filled.add(name)
    except Exception as exc:  # noqa: BLE001
        print(f"⏭️  Filling the queue failed ({type(exc).__name__}). {LOCAL_MODE}")
        return 0
    print(f"Queue {name}: {len(items)} items sent. Open Annotation Queues to see them.")
    return len(items)
