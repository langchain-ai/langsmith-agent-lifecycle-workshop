"""The keyed helpers of Module 7, checked on the requests they build. Nothing is sent.

Covers `utils/trace_upload.py` (destination, seed upload, scores, fresh traces, the review queue),
the `upload` command of `scripts/module7_seed.py` and `scripts/module7_connect_langsmith.py`.

How it stays offline: `utils.trace_upload.Client` is replaced by a function that builds the capture
client of `utils/offline_capture.py` with the settings the helpers ask for. Every request then ends
in `FakeLangSmith` below, which records it and answers the way the REST reference describes. The
whole module also runs inside `refuse_non_local_connects()`, and every test fails in `tearDown` if
any code tried to reach a non-local address or look up a host name.

Run: uv run python -m unittest tests.test_trace_upload
"""

import ast
import asyncio
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import stat
import tempfile
import threading
import typing
import unittest
import uuid
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import langsmith
from langsmith import Client, tracing_context
from langsmith import utils as ls_utils
from langsmith.types import Run, RunSelectField

from evaluators.online_evaluators import perform_eval
from utils import trace_seeding as ts
from utils import trace_upload
from utils.monitoring_local import FILTERS
from utils.offline_capture import OFFLINE_API_URL, offline_client, refuse_non_local_connects

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "22222222-2222-4222-8222-222222222222"
AGENT_PROJECT_ID = "33333333-3333-4333-8333-333333333333"
AGENT_PROJECT_NAME = "techhub-support-production"
QUEUE_ID = "44444444-4444-4444-8444-444444444444"
AGENT_ID = "techhub-support"
WORKSPACE_ID = "66666666-6666-4666-8666-666666666666"
FAKE_KEY = "lsv2_pt_not-a-real-key-0123456789abcdef"  # a made-up string in the shape of a key
PROJECT_URL = f"https://smith.langchain.com/o/{TENANT_ID}/projects/p/{PROJECT_ID}"
DOTTED_SEGMENT = re.compile(r"^\d{8}T\d{12}Z[0-9a-f-]{36}$")
ANSWERS = json.loads((ts.DATA / ts.ANSWERS_FILE).read_text(encoding="utf-8"))
WRONG_KEYS = sorted(ANSWERS["s1_evaluator"]["flagged_trace_keys"])
TAUGHT_FILTERS = {entry.filter for entry in FILTERS.values()}  # every filter string of Module 7, each paired with a Python predicate

SEED: dict = {}
NON_LOCAL_ATTEMPTS: list = []


def load_script(name: str):
    """Import one file of `scripts/` as a module (the folder is not a package)."""
    spec = importlib.util.spec_from_file_location(f"m7_script_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


connect = load_script("module7_connect_langsmith")
seed_cli = load_script("module7_seed")


def setUpModule():
    global NON_LOCAL_ATTEMPTS
    stack = ExitStack()
    NON_LOCAL_ATTEMPTS = stack.enter_context(refuse_non_local_connects())
    stack.enter_context(tracing_context(enabled=False))
    unittest.addModuleCleanup(stack.close)
    SEED.update(ts.load_seed())


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class Call:
    def __init__(self, route, method, host, path, query, body, tenant=None):
        self.route, self.method, self.host, self.path, self.query, self.body = route, method, host, path, query, body
        self.tenant = tenant  # the X-Tenant-Id header of a request sent through `client.session`, else None

    def __repr__(self):
        return f"{self.method} {self.host}{self.path}"


class FakeLangSmith:
    """Plays LangSmith for the capture adapter, and remembers every request of every client."""

    ROUTES = [
        ("batch", "POST", re.compile(r"/runs/batch$")),
        ("feedback", "POST", re.compile(r"/feedback$")),
        ("query", "POST", re.compile(r"/api/v2/runs/query$")),
        ("project", "GET", re.compile(r"/sessions(/[0-9a-f-]{36})?$")),
        ("agent", "GET", re.compile(r"/api/v1/agents/[^/]+$")),
        ("agent_create", "POST", re.compile(r"/api/v1/agents$")),
        ("queue_items", "POST", re.compile(r"/annotation-queues/[^/]+/items$")),
        ("queues", "GET", re.compile(r"/annotation-queues$")),
        ("queue_create", "POST", re.compile(r"/annotation-queues$")),
    ]

    def __init__(self):
        self.calls: list[Call] = []
        self.client_settings: list[dict] = []
        self.lock = threading.Lock()
        self.project_exists = False  # a project appears with its first trace
        self.project_id = PROJECT_ID
        self.refuse: dict[str, int] = {}  # route -> HTTP status to answer instead
        self.seeded_items: list[dict] = []  # what a query for the tag seed:m7 returns
        self.live_items: list[dict] = []  # what a query for the tag live:m7 returns
        self.agent: dict | None = None  # None: the agent does not exist (404)
        self.queue_exists = False  # True: a queue exists under every name that is asked for
        self.queue_names: set[str] = set()  # the queues created during the test, by name
        self.accepting_hosts: set[str] | None = None  # hosts that accept the key; None means every host
        # Plays an organization-scoped key: a request through `client.session` is refused unless it carries this
        # workspace id in X-Tenant-Id. Without the header the reply is the 403 the SDK turns into its own error.
        self.workspace_required: str | None = None
        self.sending = threading.local()  # the headers of the `client.session` request this thread is sending

    def client(self, **settings):
        """Stands in for `langsmith.Client` inside `utils.trace_upload`.

        Like the real class, it takes the API address from `LANGSMITH_ENDPOINT` when none is passed
        (the capture client would otherwise use its own offline address).
        """
        self.client_settings.append(settings)
        if not settings.get("api_url") and os.environ.get("LANGSMITH_ENDPOINT"):
            settings = {**settings, "api_url": os.environ["LANGSMITH_ENDPOINT"]}
        client, capture = offline_client(responder=self, **settings)
        send = capture.send

        def send_and_note_the_headers(request, **kwargs):
            # The recorder hands a responder the method, the address and the body. The workspace header is noted here.
            self.sending.headers = request.headers
            try:
                return send(request, **kwargs)
            finally:
                self.sending.headers = None

        capture.send = send_and_note_the_headers
        return client

    def __call__(self, method, url, body):
        parts = urlsplit(url)
        route = next((name for name, verb, pattern in self.ROUTES if verb == method and pattern.search(parts.path)), "other")
        headers = getattr(self.sending, "headers", None)
        tenant = headers.get("X-Tenant-Id") if headers is not None else None
        call = Call(route, method, parts.netloc, parts.path, parse_qs(parts.query), json.loads(body) if body else None, tenant)
        with self.lock:
            self.calls.append(call)
        if self.accepting_hosts is not None and parts.netloc not in self.accepting_hosts:
            return 401, {"detail": "Invalid token"}
        if self.workspace_required and headers is not None and tenant != self.workspace_required:
            if tenant is None:
                return 403, {"error": "org_scoped_key_requires_workspace"}
            return 403, {"detail": "Forbidden"}
        if route in self.refuse:
            return self.refuse[route], {"detail": "refused by the test"}
        return getattr(self, f"_{route}", lambda call: None)(call)

    def of(self, *routes) -> list[Call]:
        return [call for call in self.calls if call.route in routes]

    def _project(self, call):
        if not self.project_exists:
            return 200, []
        name = call.query.get("name", ["a-project"])[0]
        return 200, [{"id": self.project_id, "tenant_id": TENANT_ID, "name": name, "start_time": "2026-01-01T00:00:00+00:00", "reference_dataset_id": None}]

    def _batch(self, call):
        self.project_exists = True
        return 200, {}

    def _query(self, call):
        items = self.live_items if "live:m7" in call.body.get("filter", "") else self.seeded_items
        first = int(call.body.get("cursor") or 0)
        last = first + call.body.get("page_size", 100)
        return 200, {"items": items[first:last], "next_cursor": str(last) if last < len(items) else None}

    def _agent(self, call):
        return (200, self.agent) if self.agent else (404, {"detail": "Agent not found"})

    def _agent_create(self, call):
        self.agent = agent_reply(name=call.body.get("name"))
        return 200, self.agent

    def _queues(self, call):
        name = call.query["name"][0]
        return 200, [queue_reply(name)] if self.queue_exists or name in self.queue_names else []

    def _queue_create(self, call):
        self.queue_names.add(call.body["name"])
        return 200, queue_reply(call.body["name"])


def agent_reply(name="TechHub support"):
    environments = [
        {"id": f"env-{label.lower()}", "agent_id": AGENT_ID, "environment": label, "tracer_session_id": session_id, "tracer_session_name": f"{AGENT_ID}-{label.lower()}"}
        for label, session_id in (("LOCAL", "55555555-5555-4555-8555-555555555555"), ("PRODUCTION", AGENT_PROJECT_ID))
    ]
    return {"id": AGENT_ID, "name": name, "source_type": "EXTERNAL", "agent_type": "CUSTOM", "created_at": "2026-11-19T00:00:00Z", "environments": environments}


def queue_reply(name):
    return {"id": QUEUE_ID, "name": name, "tenant_id": TENANT_ID, "created_at": "2026-11-19T00:00:00Z", "updated_at": "2026-11-19T00:00:00Z"}


def stored_roots(scored="all", only=None):
    """The seeded root runs as a query for the tag seed:m7 returns them, for a workspace that an earlier process uploaded to.

    `scored` says which runs already carry their user score: "all" of the rated ones, "none", or a
    number (the first so many rated runs). `only` keeps the first so many root runs (a cut-short upload).
    """
    rated = [row["trace_key"] for row in SEED["feedback"]]
    with_score = set(rated if scored == "all" else [] if scored == "none" else rated[:scored])
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    items = [
        {"id": str(uuid.uuid4()), "trace_id": None, "start_time": (start + timedelta(seconds=i)).isoformat(),
         "metadata": {"seed_trace_key": ts.trace_key(run)},
         "feedback_stats": {"user_score": {"n": 1, "avg": 1.0}} if ts.trace_key(run) in with_score else {}}
        for i, run in enumerate(ts.root_runs(SEED))
    ]
    return items if only is None else items[:only]


def stored_from(posted):
    """What a query returns for root runs that this test's upload posted, none of them scored yet."""
    return [
        {"id": run["id"], "trace_id": run["trace_id"], "start_time": run["start_time"], "metadata": run["extra"]["metadata"], "feedback_stats": {}}
        for run in posted if run["parent_run_id"] is None
    ]


def said(function, *args, **kwargs):
    """Call a helper and return `(result, what it printed)`."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = function(*args, **kwargs)
    return result, out.getvalue()


class KeyedTestCase(unittest.TestCase):
    def setUp(self):
        self.server = FakeLangSmith()
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        # Whatever the caller's shell or `.env` sets, each test starts from the same environment.
        for name in ("M7_PROJECT", "TECHHUB_AGENT_ID", "TECHHUB_AGENT_ENVIRONMENT", "LANGSMITH_AGENT_ID", "LANGSMITH_AGENT_ENVIRONMENT",
                     "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGSMITH_WORKSPACE_ID"):
            os.environ.pop(name, None)
        ls_utils.get_env_var.cache_clear()
        for patcher in (mock.patch.object(trace_upload, "Client", self.server.client), mock.patch.object(trace_upload, "_sleep", lambda seconds: None)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(setattr, trace_upload, "_last_destination", None)
        # The SDK remembers the environment variables it has read; forget them so no test sees another's.
        self.addCleanup(ls_utils.get_env_var.cache_clear)

    def tearDown(self):
        attempts, NON_LOCAL_ATTEMPTS[:] = list(NON_LOCAL_ATTEMPTS), []
        self.assertEqual(attempts, [], "this test tried to leave the machine")

    def destination(self, available=True):
        destination, _ = said(trace_upload.resolve_destination, available)
        return destination

    def uploaded(self):
        """A destination after one successful upload, with the server's record emptied."""
        destination = self.destination()
        seeded, _ = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded)
        self.server.calls.clear()
        return destination

    def posted(self, calls=None):
        return [run for call in (self.server.of("batch") if calls is None else calls) for run in call.body.get("post", [])]

    def patched(self, calls=None):
        return [run for call in (self.server.of("batch") if calls is None else calls) for run in call.body.get("patch", [])]

    def assert_every_query_names_a_start_time(self):
        for call in self.server.of("query"):
            self.assertIn("min_start_time", call.body, "runs.query looks back one day unless min_start_time is given")
            self.assertTrue(call.body["is_root"])
            self.assertEqual(len(call.body["project_ids"]), 1)
            self.assertIn(call.body["filter"], TAUGHT_FILTERS, "a filter string was sent that the notebook does not teach")

    def assert_nothing_creates_or_deletes_a_project(self):
        for call in self.server.calls:
            self.assertNotEqual(call.method, "DELETE", call)
            self.assertFalse(call.method == "POST" and call.path.rstrip("/").endswith("/sessions"), f"{call} would create a project")


class DestinationTest(KeyedTestCase):
    def test_without_a_key_nothing_is_asked_and_nothing_is_printed(self):
        destination, printed = said(trace_upload.resolve_destination, False)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(printed, "")
        self.assertFalse(destination.available)
        self.assertEqual(destination.project_name, "techhub-deep-agent-production")
        self.assertIsNone(destination.project_id)
        self.assertEqual(destination.where, "Tracing > project 'techhub-deep-agent-production'")
        self.assertIs(destination.refresh(), destination)
        self.assertEqual(self.server.calls, [])

    def test_the_project_name_comes_from_m7_project(self):
        os.environ["M7_PROJECT"] = "my-own-project"
        self.assertEqual(self.destination(False).project_name, "my-own-project")
        self.assertEqual(said(trace_upload.resolve_destination, False, project_name="named-in-code")[0].project_name, "named-in-code")

    def test_with_a_key_a_new_workspace_has_no_project_id_yet(self):
        destination, printed = said(trace_upload.resolve_destination, True)
        self.assertEqual(printed, "Seeded traffic goes to: Tracing > project 'techhub-deep-agent-production'\n")
        self.assertTrue(destination.available)
        self.assertIsNone(destination.project_id)
        self.assertEqual([(call.method, call.path) for call in self.server.calls], [("GET", "/sessions")])
        self.assertEqual(self.server.calls[0].query["name"], ["techhub-deep-agent-production"])
        self.assert_nothing_creates_or_deletes_a_project()

    def test_refresh_finds_the_project_once_it_exists(self):
        destination = self.destination()
        self.server.project_exists = True
        self.assertIs(destination.refresh(), destination)
        self.assertEqual(destination.project_id, PROJECT_ID)
        self.assertEqual(destination.url, PROJECT_URL)

    def test_a_rejected_key_does_not_raise(self):
        self.server.refuse["project"] = 401
        with self.assertNoLogs("langsmith", level="WARNING"):
            destination = self.destination()
        self.assertIsNone(destination.project_id)

    def test_the_agent_addressing_variables_are_removed_from_the_process(self):
        os.environ.update({"LANGSMITH_AGENT_ID": "some-agent", "LANGSMITH_AGENT_ENVIRONMENT": "production"})
        self.destination(False)
        self.assertNotIn("LANGSMITH_AGENT_ID", os.environ)
        self.assertNotIn("LANGSMITH_AGENT_ENVIRONMENT", os.environ)

    def test_the_client_settings_keep_the_upload_equal_to_the_seed(self):
        self.destination()
        settings = self.server.client_settings[-1]
        self.assertFalse(settings["auto_batch_tracing"])
        self.assertTrue(settings["omit_traced_runtime_info"])
        self.assertEqual((settings["hide_inputs"], settings["hide_outputs"], settings["hide_metadata"]), (False, False, False))
        self.assertEqual(settings["tracing_sampling_rate"], 1.0)

    def test_the_navigation_sentence_names_the_place_and_the_time_range(self):
        sentence = self.destination(False).navigation
        self.assertIn("tracing project 'techhub-deep-agent-production'", sentence)
        self.assertIn("at least the last 2 days", sentence)

    def test_the_navigation_sentence_says_what_to_run_again_wherever_it_is_printed(self):
        # The sentence is printed by notebooks and by two scripts. "run the Setup cell again" alone fits only the first.
        destination = self.destination(False)
        self.assertEqual(destination.navigation, destination.how_to_find())
        self.assertTrue(destination.navigation.endswith("set TECHHUB_AGENT_ID in .env and repeat this step (in a notebook, run the Setup cell again)."), destination.navigation)
        named = destination.how_to_find(rerun="run `the command` again")
        self.assertTrue(named.endswith("agent-based: set TECHHUB_AGENT_ID in .env and run `the command` again."), named)
        self.assertNotIn("Setup cell", named)
        self.assertIn("control at the top left shows your workspace name instead of the LangSmith logo", named)


class AgentBasedDestinationTest(KeyedTestCase):
    def setUp(self):
        super().setUp()
        os.environ["TECHHUB_AGENT_ID"] = AGENT_ID
        self.server.project_id = AGENT_PROJECT_ID

    def test_an_existing_agent_gives_its_production_project(self):
        self.server.agent = agent_reply()
        destination, printed = said(trace_upload.resolve_destination, True)
        self.assertEqual(printed, "Seeded traffic goes to: Tracing > agent 'TechHub support' > environment Production\n")
        self.assertEqual([(call.method, call.path) for call in self.server.of("agent")], [("GET", f"/api/v1/agents/{AGENT_ID}")])
        self.assertEqual(self.server.of("agent_create"), [])
        self.assertEqual(destination.project_name, AGENT_PROJECT_NAME)  # the returned tracer_session_name
        self.assertEqual(destination.project_id, AGENT_PROJECT_ID)
        self.assertIn("select the agent 'TechHub support'", destination.navigation)
        self.assert_nothing_creates_or_deletes_a_project()

    def test_the_upload_goes_to_the_project_the_agent_names(self):
        self.server.agent = agent_reply()
        destination = self.destination()
        seeded, _ = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded)
        self.assertEqual({run["session_name"] for run in self.posted()}, {AGENT_PROJECT_NAME})
        self.assertEqual({call.body["session_id"] for call in self.server.of("feedback")}, {AGENT_PROJECT_ID})
        self.assertEqual(self.server.of("query")[0].body["project_ids"], [AGENT_PROJECT_ID])
        self.assert_every_query_names_a_start_time()
        self.assert_nothing_creates_or_deletes_a_project()

    def test_a_missing_agent_is_created_as_an_external_agent(self):
        destination = self.destination()
        self.assertEqual(self.server.of("agent_create")[0].body, {"id": AGENT_ID, "name": "TechHub support", "source_type": "EXTERNAL"})
        self.assertEqual(destination.project_name, AGENT_PROJECT_NAME)
        self.assertTrue(destination.available)

    def test_another_environment_can_be_chosen(self):
        self.server.agent = agent_reply()
        os.environ["TECHHUB_AGENT_ENVIRONMENT"] = "local"
        destination = self.destination()
        self.assertEqual(destination.project_name, f"{AGENT_ID}-local")
        self.assertEqual(destination.where, "Tracing > agent 'TechHub support' > environment Local")

    def test_any_failure_means_local_mode_with_one_line(self):
        for refused in ({"agent": 403}, {"agent_create": 403}):
            with self.subTest(refused=refused):
                self.server.refuse = refused
                self.server.agent = None
                with self.assertNoLogs("langsmith", level="WARNING"):
                    destination, printed = said(trace_upload.resolve_destination, True)
                self.assertFalse(destination.available)
                self.assertEqual(printed.count("\n"), 1)
                self.assertRegex(printed, r"^⏭️  Could not use the agent 'techhub-support' as the destination \(\w+\)\. Continuing in local mode\.\n$")
                self.server.calls.clear()
                self.assertFalse(said(trace_upload.upload_seed, SEED, destination)[0])
                self.assertEqual(self.server.calls, [])

    def test_an_incomplete_upload_names_the_agent_environment_as_the_way_out(self):
        self.server.agent = agent_reply()
        self.server.project_exists = True
        self.server.seeded_items = stored_roots(only=40)
        seeded, printed = said(trace_upload.upload_seed, SEED, self.destination())
        self.assertFalse(seeded)
        self.assertIn("holds 40 of the 260 seeded traces", printed)
        self.assertIn("TECHHUB_AGENT_ENVIRONMENT", printed)
        self.assertNotIn("M7_PROJECT", printed)

    def test_an_environment_the_agent_does_not_have_means_local_mode(self):
        self.server.agent = agent_reply()
        os.environ["TECHHUB_AGENT_ENVIRONMENT"] = "staging"
        destination, printed = said(trace_upload.resolve_destination, True)
        self.assertFalse(destination.available)
        self.assertIn("(LookupError)", printed)


class UploadSeedTest(KeyedTestCase):
    def test_runs_go_out_as_create_batches_followed_by_update_batches(self):
        before = fingerprint(SEED)
        destination = self.destination()
        started = datetime.now(timezone.utc)
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded)
        self.assertEqual(fingerprint(SEED), before, "upload_seed changed the seed it was given")

        batches = self.server.of("batch")
        kinds = ["create" if "post" in call.body else "update" for call in batches]
        self.assertEqual(kinds, ["create"] * 14 + ["update"] * 14)
        for call in batches:
            self.assertEqual(len(call.body), 1, "a batch is either a create batch or an update batch")
            self.assertLessEqual(len(next(iter(call.body.values()))), 250)
        posted, patched = self.posted(), self.patched()
        self.assertEqual(len(posted), len(SEED["runs"]))
        self.assertEqual([run["id"] for run in patched], [run["id"] for run in posted])

        # All 260 traces, each under a new version-7 id; a root run's id is its trace id.
        roots = [run for run in posted if run["parent_run_id"] is None]
        self.assertEqual(len(roots), 260)
        self.assertEqual(len({run["trace_id"] for run in posted}), 260)
        old_ids = {run["id"] for run in SEED["runs"]}
        seen = set()
        for run in posted:
            self.assertEqual(uuid.UUID(run["id"]).version, 7)
            self.assertNotIn(run["id"], old_ids)
            self.assertTrue(run["parent_run_id"] is None or run["parent_run_id"] in seen, "a child was sent before its parent")
            seen.add(run["id"])
            segments = run["dotted_order"].split(".")
            self.assertTrue(all(DOTTED_SEGMENT.match(segment) for segment in segments))
            self.assertTrue(segments[-1].endswith(run["id"]))
            self.assertEqual(segments[0][-36:], run["trace_id"])
            self.assertEqual(run["session_name"], "techhub-deep-agent-production")
            self.assertEqual(run["tags"], ["seed:m7"])
            self.assertNotIn("runtime", run["extra"])
        for run in roots:
            self.assertEqual(run["id"], run["trace_id"])
        for run in patched:
            self.assertIn("end_time", run)
            self.assertTrue(run["dotted_order"])
        self.assertEqual(sum(1 for run in patched if run["parent_run_id"] is None and run.get("error")), 13)

        # Nothing is added to the metadata, and every thread id gets the same per-upload suffix.
        seed_metadata = {ts.trace_key(run): run["extra"]["metadata"] for run in ts.root_runs(SEED)}
        suffixes = set()
        for run in roots:
            metadata = run["extra"]["metadata"]
            original = seed_metadata[metadata["seed_trace_key"]]
            self.assertEqual(set(metadata), set(original))
            self.assertTrue(metadata["thread_id"].startswith(original["thread_id"] + "-"))
            suffixes.add(metadata["thread_id"][len(original["thread_id"]):])
        self.assertEqual(len(suffixes), 1)
        self.assertRegex(suffixes.pop(), r"^-[0-9a-f]{6}$")

        # Timestamps are shifted again at upload time: the newest root run started 5 minutes ago.
        newest = max(datetime.fromisoformat(run["start_time"]) for run in roots)
        self.assertLess(abs((started - timedelta(minutes=5) - newest).total_seconds()), 30)

        # The 170 user scores, each naming the project and leaving retention alone.
        feedback = self.server.of("feedback")
        self.assertEqual(len(feedback), 170)
        root_ids = {run["id"] for run in roots}
        for call in feedback:
            self.assertEqual(call.body["session_id"], PROJECT_ID)
            self.assertIs(call.body["extend_trace_retention"], False)
            self.assertEqual(call.body["key"], "user_score")
            self.assertIn(call.body["run_id"], root_ids)
            self.assertEqual(call.body["trace_id"], call.body["run_id"])
            self.assertIn("start_time", call.body)
        self.assertEqual(Counter(call.body["score"] for call in feedback), {1: 145, 0: 25})
        self.assertGreater(self.server.calls.index(feedback[0]), self.server.calls.index(batches[-1]), "scores were written before the runs")

        # A new workspace has no project to ask about, so there was no guard query; nothing created one.
        self.assertEqual(self.server.of("query"), [])
        self.assert_nothing_creates_or_deletes_a_project()

        self.assertEqual(printed.splitlines()[0], f"Uploaded 260 traces and 170 user scores. 📊 {PROJECT_URL}")
        self.assertIn("Tracing > project 'techhub-deep-agent-production'", printed.splitlines()[1])
        self.assertEqual(destination.project_id, PROJECT_ID)
        self.assertEqual(sorted(destination.uploaded), sorted(seed_metadata))
        self.assertEqual({entry["run_id"] for entry in destination.uploaded.values()}, root_ids)

    def test_an_existing_project_is_asked_for_an_earlier_upload_first(self):
        self.server.project_exists = True
        destination = self.destination()
        asked = datetime.now(timezone.utc)
        self.assertTrue(said(trace_upload.upload_seed, SEED, destination)[0])
        guard = self.server.of("query")
        self.assertEqual(len(guard), 1)
        body = guard[0].body
        self.assertEqual(body["filter"], 'has(tags, "seed:m7")')
        self.assertEqual((body["project_ids"], body["is_root"], body["page_size"], body["selects"]), ([PROJECT_ID], True, 1, ["ID"]))
        since = datetime.fromisoformat(body["min_start_time"])
        self.assertLess(abs((asked - timedelta(days=7) - since).total_seconds()), 30)
        self.assertLess(self.server.calls.index(guard[0]), self.server.calls.index(self.server.of("batch")[0]), "the guard must come before the upload")
        self.assertEqual(len(self.posted()), len(SEED["runs"]))
        self.assert_every_query_names_a_start_time()

    def test_with_the_seeded_day_already_there_nothing_is_uploaded(self):
        self.server.project_exists = True
        self.server.seeded_items = stored_roots()
        destination = self.destination()
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded, "the workspace holds the seeded day, so later keyed cells may run")
        self.assertEqual(self.server.of("batch", "feedback"), [])
        self.assertEqual(printed.count("\n"), 1)
        self.assertIn("Already uploaded", printed)
        self.assertIn("Nothing was sent", printed)
        self.assert_every_query_names_a_start_time()
        # The guard asks for one run; the completeness check then reads all 260 in pages of 100.
        self.assertEqual([call.body["page_size"] for call in self.server.of("query")], [1, 100, 100, 100])
        self.assertLessEqual({"ID", "METADATA", "FEEDBACK_STATS"}, set(self.server.of("query")[1].body["selects"]))
        self.assertEqual(len(destination.uploaded), 260, "later keyed cells find the uploaded runs without asking again")

    def test_an_earlier_upload_that_stopped_part_way_is_not_reported_as_done(self):
        # Before: one root run tagged seed:m7 was enough for "Already uploaded" and True, whatever was missing.
        self.server.project_exists = True
        self.server.seeded_items = stored_roots(only=100)
        destination = self.destination()
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                self.server.calls.clear()
                seeded, printed = said(trace_upload.upload_seed, SEED, destination)
                self.assertFalse(seeded)
                self.assertEqual(printed.count("\n"), 1)
                self.assertTrue(printed.startswith("⏭️  Incomplete upload: Tracing > project 'techhub-deep-agent-production' holds 100 of the 260 seeded traces"), printed)
                self.assertIn("set M7_PROJECT in .env to a project name that does not exist yet", printed)
                self.assertIn("wait and run this again", printed)
                self.assertTrue(printed.rstrip().endswith("Continuing in local mode."))
                self.assertEqual(self.server.of("batch", "feedback"), [], "nothing may be added to a half-filled project")
                self.assertEqual(len(self.server.of("query")), 3, "the guard, then the read, repeated once before it is called incomplete")
                self.assert_every_query_names_a_start_time()
        self.assertEqual(destination.uploaded, {})

    def test_an_earlier_upload_without_its_user_scores_gets_them(self):
        for scored, missing in (("none", 170), (100, 70)):
            with self.subTest(scored=scored):
                self.server.calls.clear()
                self.server.project_exists = True
                self.server.seeded_items = stored_roots(scored=scored)
                destination = self.destination()
                seeded, printed = said(trace_upload.upload_seed, SEED, destination)
                self.assertTrue(seeded)
                self.assertEqual(self.server.of("batch"), [], "the runs are there: none may be sent again")
                feedback = self.server.of("feedback")
                self.assertEqual(len(feedback), missing)
                by_key = {item["metadata"]["seed_trace_key"]: item for item in self.server.seeded_items}
                unscored = {by_key[row["trace_key"]]["id"]: row["score"] for row in SEED["feedback"] if not by_key[row["trace_key"]]["feedback_stats"]}
                self.assertEqual({call.body["run_id"]: call.body["score"] for call in feedback}, unscored)
                for call in feedback:
                    self.assertEqual((call.body["key"], call.body["session_id"]), ("user_score", PROJECT_ID))
                    self.assertIs(call.body["extend_trace_retention"], False)
                self.assertEqual(printed.count("\n"), 1)
                self.assertIn(f"No run was sent; {missing} user scores were missing and have been written.", printed)
                self.assertEqual(destination.pending_scores, [])

    def test_scores_that_failed_after_the_runs_were_sent_are_written_by_the_next_call(self):
        # Before: the first call returned False, and every later call found a run tagged seed:m7,
        # said "Already uploaded" and returned True. The 170 user scores were never written.
        self.server.refuse["feedback"] = 403
        destination = self.destination()
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertRegex(printed, r"^⏭️  Upload failed \(\w+\)\. Continuing in local mode\.\n$")
        self.assertEqual(len(self.posted()), len(SEED["runs"]), "all runs reached the server before the failure")
        self.assertEqual(len(destination.pending_scores), 170)
        root_ids = {run["id"] for run in self.posted() if run["parent_run_id"] is None}

        self.server.refuse.clear()
        self.server.calls.clear()
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded)
        self.assertEqual(self.server.of("batch"), [], "the runs must not be sent a second time")
        feedback = self.server.of("feedback")
        self.assertEqual(len(feedback), 170)
        self.assertEqual(len({call.body["run_id"] for call in feedback}), 170)
        self.assertLessEqual({call.body["run_id"] for call in feedback}, root_ids)
        self.assertEqual({call.body["session_id"] for call in feedback}, {PROJECT_ID})
        self.assertIn("Wrote the 170 user scores that were missing", printed)
        self.assertEqual(destination.pending_scores, [])

        self.server.calls.clear()
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded)
        self.assertEqual(self.server.calls, [])
        self.assertIn("Already uploaded in this session", printed)

    def test_scores_that_stopped_half_way_are_completed_without_writing_one_twice(self):
        accepted: list[str] = []

        def feedback_until_forty(server, call):
            with server.lock:
                if server.refuse_scores and len(accepted) >= 40:
                    return 403, {"detail": "refused by the test"}
                accepted.append(call.body["run_id"])
            return 200, {}

        self.server.refuse_scores = True
        destination = self.destination()
        with mock.patch.object(FakeLangSmith, "_feedback", feedback_until_forty, create=True):
            self.assertFalse(said(trace_upload.upload_seed, SEED, destination)[0])
            self.assertEqual(len(accepted), 40)
            self.assertEqual(len(destination.pending_scores), 130)
            self.server.refuse_scores = False
            self.assertTrue(said(trace_upload.upload_seed, SEED, destination)[0])
        self.assertEqual(len(accepted), 170)
        self.assertEqual(len(set(accepted)), 170, "a score that was accepted the first time must not be written again")

    def test_a_new_process_finds_the_runs_and_writes_the_scores_that_are_missing(self):
        # The same failure, seen from a process that remembers nothing: the key-entry script failed, then a notebook starts.
        self.server.refuse["feedback"] = 403
        self.assertFalse(said(trace_upload.upload_seed, SEED, self.destination())[0])
        self.server.seeded_items = stored_from(self.posted())
        self.server.refuse.clear()
        self.server.calls.clear()
        fresh = self.destination()
        self.assertEqual((fresh.uploaded, fresh.pending_scores), ({}, []))
        seeded, printed = said(trace_upload.upload_seed, SEED, fresh)
        self.assertTrue(seeded)
        self.assertEqual(self.server.of("batch"), [])
        self.assertEqual(len(self.server.of("feedback")), 170)
        self.assertEqual({call.body["run_id"] for call in self.server.of("feedback")} - {item["id"] for item in self.server.seeded_items}, set())
        self.assertIn("170 user scores were missing and have been written", printed)

    def test_an_upload_that_stopped_between_two_batches_is_reported_as_incomplete(self):
        batches = []

        def three_batches_then_refuse(server, call):
            batches.append(call)
            server.project_exists = True
            return (200, {}) if len(batches) <= 3 else (403, {"detail": "refused by the test"})

        destination = self.destination()
        with mock.patch.object(FakeLangSmith, "_batch", three_batches_then_refuse):
            seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertRegex(printed, r"^⏭️  Upload failed \(\w+\)\. Continuing in local mode\.\n$")
        self.assertTrue(destination.partial)
        self.assertEqual(destination.uploaded, {})
        there = stored_from([run for call in batches[:3] for run in call.body["post"]])
        self.assertTrue(0 < len(there) < 260)

        # The same process: it knows, and asks nothing.
        self.server.calls.clear()
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(printed.count("\n"), 1)
        self.assertIn("Incomplete upload", printed)
        self.assertIn("holds only some of the 260 seeded traces", printed)

        # A new process: it counts what is there.
        self.server.seeded_items = there
        seeded, printed = said(trace_upload.upload_seed, SEED, self.destination())
        self.assertFalse(seeded)
        self.assertIn(f"holds {len(there)} of the 260 seeded traces", printed)
        self.assertEqual(self.server.of("batch", "feedback"), [])

    def test_a_batch_refused_before_anything_was_accepted_can_simply_be_repeated(self):
        self.server.refuse["batch"] = 403
        destination = self.destination()
        self.assertFalse(said(trace_upload.upload_seed, SEED, destination)[0])
        self.assertFalse(destination.partial, "nothing reached the project, so there is nothing to clean up")
        self.server.refuse.clear()
        self.assertTrue(said(trace_upload.upload_seed, SEED, destination)[0])
        self.assertEqual(len(destination.uploaded), 260)

    def test_a_second_call_in_the_same_session_sends_nothing(self):
        destination = self.uploaded()
        seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertTrue(seeded)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(printed, "Already uploaded in this session: 260 traces are in Tracing > project 'techhub-deep-agent-production'. Nothing was sent.\n")

    def test_a_refused_batch_returns_false_and_prints_one_line(self):
        self.server.refuse["batch"] = 403
        destination = self.destination()
        with self.assertNoLogs("langsmith", level="WARNING"):
            seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertRegex(printed, r"^⏭️  Upload failed \(\w+\)\. Continuing in local mode\.\n$")
        self.assertEqual(len(self.server.of("batch")), 1, "the upload must stop at the first refused batch")
        self.assertEqual(self.server.of("feedback"), [])
        self.assertEqual(destination.uploaded, {})

    def test_a_refused_score_returns_false_and_prints_one_line(self):
        self.server.refuse["feedback"] = 403
        destination = self.destination()
        with self.assertNoLogs("langsmith", level="WARNING"):
            seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertRegex(printed, r"^⏭️  Upload failed \(\w+\)\. Continuing in local mode\.\n$")
        self.assertEqual(len(self.server.of("feedback")), 1, "the first refused score must stop the rest")

    def test_a_rejected_key_returns_false_and_prints_one_line(self):
        destination = self.destination()
        self.server.refuse["project"] = 401
        with self.assertNoLogs("langsmith", level="WARNING"):
            seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertEqual(printed, "⏭️  Upload failed (LangSmithAuthError). Continuing in local mode.\n")
        self.assertEqual(self.server.of("batch", "feedback"), [])

    def test_any_exception_inside_the_upload_returns_false_and_prints_one_line(self):
        destination = self.destination()
        with mock.patch.object(trace_upload, "remap_ids", side_effect=RuntimeError("boom")):
            seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertEqual(printed, "⏭️  Upload failed (RuntimeError). Continuing in local mode.\n")

    def test_a_project_that_cannot_be_read_after_the_upload_is_a_failed_upload(self):
        destination = self.destination()
        with mock.patch.object(FakeLangSmith, "_batch", lambda self, call: (200, {})):  # the project never appears
            seeded, printed = said(trace_upload.upload_seed, SEED, destination)
        self.assertFalse(seeded)
        self.assertEqual(printed, "⏭️  Upload failed (LookupError). Continuing in local mode.\n")
        self.assertEqual(self.server.of("feedback"), [])

    def test_without_a_key_nothing_is_sent(self):
        seeded, printed = said(trace_upload.upload_seed, SEED, self.destination(False))
        self.assertFalse(seeded)
        self.assertTrue(printed.startswith("⏭️  Skipped"))
        self.assertEqual(self.server.calls, [])

    def test_a_dry_run_prints_the_counts_and_makes_no_request(self):
        seeded, printed = said(trace_upload.upload_seed, SEED, self.destination(False), dry_run=True)
        self.assertFalse(seeded)
        self.assertEqual(self.server.calls, [])
        self.assertIn("Dry run: nothing is sent.", printed)
        self.assertIn("28 (14 create, then 14 update; at most 250 runs each)", printed)
        self.assertIn("feedback calls: 170", printed)
        self.assertEqual(trace_upload.upload_plan(SEED), {"traces": 260, "runs": len(SEED["runs"]), "create_batches": 14, "update_batches": 14, "batch_size": 250, "feedback_calls": 170})

    def test_it_also_works_where_an_event_loop_is_already_running(self):
        # A notebook cell runs inside an event loop, where asyncio.run() is not allowed.
        self.server.project_exists = True
        destination = self.destination()

        async def cell():
            return said(trace_upload.upload_seed, SEED, destination)[0]

        self.assertTrue(asyncio.run(cell()))
        self.assertEqual(len(self.server.of("query")), 1)
        self.assertEqual(len(self.server.of("feedback")), 170)

    def test_the_tag_filters_are_the_strings_taught_in_the_notebook(self):
        self.assertEqual(trace_upload.SEEDED_FILTER, FILTERS["seeded_runs"].filter)
        self.assertEqual(trace_upload.LIVE_FILTER, FILTERS["live_runs"].filter)


class WriteScoresTest(KeyedTestCase):
    def test_every_root_run_gets_a_score_and_eleven_are_flagged(self):
        destination = self.uploaded()
        result, printed = said(trace_upload.write_scores, SEED, destination, perform_eval)
        self.assertEqual(result, {"written": 260, "flagged": {"wrong_return_window": 11}})
        self.assertEqual(printed, "Wrote 260 scores. 11 runs carry wrong_return_window = 1.\n")
        feedback = self.server.of("feedback")
        self.assertEqual(len(feedback), 260)
        self.assertEqual(len(self.server.calls), 260, "write_scores must send scores and nothing else")
        for call in feedback:
            self.assertEqual(call.body["key"], "wrong_return_window")
            self.assertEqual(call.body["session_id"], PROJECT_ID)
            self.assertIs(call.body["extend_trace_retention"], False)
            self.assertIn("start_time", call.body)
        by_run = {entry["run_id"]: key for key, entry in destination.uploaded.items()}
        self.assertEqual(sorted(by_run[call.body["run_id"]] for call in feedback), sorted(by_run.values()))
        self.assertEqual(sorted(by_run[call.body["run_id"]] for call in feedback if call.body["score"] == 1), WRONG_KEYS)
        self.assertEqual({call.body["score"] for call in feedback}, {0, 1})

    def test_a_second_call_in_the_same_session_writes_nothing(self):
        destination = self.uploaded()
        said(trace_upload.write_scores, SEED, destination, perform_eval)
        self.server.calls.clear()
        result, printed = said(trace_upload.write_scores, SEED, destination, perform_eval)
        self.assertEqual(result, {"written": 0, "flagged": {"wrong_return_window": 11}})
        self.assertEqual(self.server.calls, [])
        self.assertIn("Already written in this session", printed)

    def test_a_bug_in_the_evaluator_is_raised_and_not_reported_as_a_langsmith_failure(self):
        destination = self.uploaded()

        def broken(run, example=None):
            return {"wrong_return_window": run["no_such_key"]}

        with self.assertRaises(KeyError):
            trace_upload.write_scores(SEED, destination, broken)
        self.assertEqual(self.server.calls, [])

    def test_a_failed_write_can_be_repeated(self):
        destination = self.uploaded()
        self.server.refuse["feedback"] = 403
        said(trace_upload.write_scores, SEED, destination, perform_eval)
        self.server.refuse.clear()
        self.assertEqual(said(trace_upload.write_scores, SEED, destination, perform_eval)[0]["written"], 260)

    def test_after_a_restart_the_uploaded_runs_are_read_back_from_langsmith(self):
        self.server.project_exists = True
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        self.server.seeded_items = [
            {"id": str(uuid.uuid4()), "trace_id": None, "start_time": (start + timedelta(seconds=i)).isoformat(), "metadata": {"seed_trace_key": ts.trace_key(run)}}
            for i, run in enumerate(ts.root_runs(SEED))
        ]
        destination = self.destination()  # a fresh process: nothing is remembered from an upload
        self.assertEqual(destination.uploaded, {})
        result, _ = said(trace_upload.write_scores, SEED, destination, perform_eval)
        self.assertEqual(result, {"written": 260, "flagged": {"wrong_return_window": 11}})
        query = self.server.of("query")
        self.assertEqual([call.body.get("cursor") for call in query], [None, "100", "200"], "260 runs are read in pages of 100")
        for call in query:
            self.assertEqual(call.body["filter"], 'has(tags, "seed:m7")')
            self.assertLessEqual({"ID", "START_TIME", "METADATA"}, set(call.body["selects"]))
        self.assert_every_query_names_a_start_time()
        sent_to = {call.body["run_id"] for call in self.server.of("feedback")}
        self.assertEqual(sent_to, {item["id"] for item in self.server.seeded_items})
        self.assertEqual(self.server.of("batch"), [])

    def test_with_nothing_uploaded_nothing_is_written(self):
        self.server.project_exists = True
        result, printed = said(trace_upload.write_scores, SEED, self.destination(), perform_eval)
        self.assertEqual(result, {"written": 0, "flagged": {}})
        self.assertTrue(printed.startswith("⏭️  Skipped"))
        self.assertEqual(self.server.of("feedback"), [])

    def test_a_refused_score_prints_one_line(self):
        destination = self.uploaded()
        self.server.refuse["feedback"] = 403
        with self.assertNoLogs("langsmith", level="WARNING"):
            result, printed = said(trace_upload.write_scores, SEED, destination, perform_eval)
        self.assertEqual(result, {"written": 0, "flagged": {}})
        self.assertRegex(printed, r"^⏭️  Writing scores failed \(\w+\)\. Continuing in local mode\.\n$")

    def test_without_a_key_nothing_is_sent(self):
        result, _ = said(trace_upload.write_scores, SEED, self.destination(False), perform_eval)
        self.assertEqual(result["written"], 0)
        self.assertEqual(self.server.calls, [])


class LiveTracesTest(KeyedTestCase):
    def roots(self):
        """The fresh root runs as LangSmith would hold them: the create payload completed by its update."""
        ends = {run["id"]: run for run in self.patched()}
        return [{**run, **ends[run["id"]]} for run in self.posted() if run["parent_run_id"] is None]

    def test_quality_sends_four_fresh_traces_and_the_evaluator_flags_two(self):
        self.destination()
        before = datetime.now(timezone.utc)
        sent, printed = said(trace_upload.send_live_traces, "quality", 4)
        after = datetime.now(timezone.utc)
        self.assertEqual(sent, 4)
        self.assertEqual(printed, "Sent 4 fresh traces (2 give the wrong window). Refresh the feedback column.\n")
        roots = self.roots()
        self.assertEqual(len(roots), 4)
        for run in roots:
            self.assertEqual(run["tags"], ["live:m7"])
            self.assertEqual(run["name"], "deep_support_agent")
            self.assertEqual(run["id"], run["trace_id"])
            self.assertEqual(uuid.UUID(run["id"]).version, 7)
            started, ended = datetime.fromisoformat(run["start_time"]), datetime.fromisoformat(run["end_time"])
            self.assertGreater(started, before - timedelta(seconds=60), "a fresh root run must start within the last minute")
            self.assertLessEqual(ended, after, "a fresh trace must not end in the future")
            self.assertEqual(run["extra"]["metadata"]["app_version"], "1.5.0")
            self.assertIs(run["extra"]["metadata"]["synthetic"], True)
        self.assertEqual(sum(1 for run in roots if perform_eval(run)["wrong_return_window"]), 2)
        self.assertEqual(sum(1 for run in roots if "30 days" in ts.reply_text(run)), 4, "all four are return-window answers")
        self.assertEqual(len({run["extra"]["metadata"]["thread_id"] for run in roots}), 4)
        self.assertEqual(sorted(run["extra"]["metadata"]["seed_trace_key"] for run in roots), ["lq-01", "lq-02", "lq-03", "lq-04"])
        seed_ids = {run["id"] for run in SEED["runs"]}
        posted = self.posted()
        self.assertTrue(all(run["tags"] == ["live:m7"] and run["id"] not in seed_ids for run in posted))
        self.assertEqual({run["session_name"] for run in posted}, {"techhub-deep-agent-production"})
        self.assertEqual(["create" if "post" in call.body else "update" for call in self.server.of("batch")], ["create", "update"])
        self.assertEqual(sorted(run["id"] for run in posted), sorted(run["id"] for run in self.patched()))
        self.assert_nothing_creates_or_deletes_a_project()

    def test_errors_sends_five_errored_root_runs_dated_now(self):
        self.destination()
        before = datetime.now(timezone.utc)
        sent, printed = said(trace_upload.send_live_traces, "errors", 5)
        self.assertEqual(sent, 5)
        self.assertEqual(printed, "Sent 5 errored runs dated now. When the alert fires is not documented.\n")
        roots = self.roots()
        self.assertEqual(len(roots), 5)
        for run in roots:
            self.assertEqual(run["tags"], ["live:m7"])
            self.assertEqual(run["name"], "deep_support_agent")
            self.assertEqual(run["error"], "OrderServiceUnavailable: get_order_status timed out")
            self.assertGreater(datetime.fromisoformat(run["start_time"]), before - timedelta(seconds=60))
        failed_tools = [run for run in self.patched() if run.get("error") and run["id"] in {r["id"] for r in self.posted() if r["name"] == "get_order_status"}]
        self.assertEqual(len(failed_tools), 5)

    def test_built_traces_keep_whole_trees_and_fresh_ids_each_time(self):
        first, wrong = trace_upload.build_live_traces("quality", 4)
        second, _ = trace_upload.build_live_traces("quality", 4)
        self.assertEqual(wrong, 2)
        self.assertEqual(len(first), len(second))
        self.assertFalse({run["id"] for run in first} & {run["id"] for run in second})
        ids = {run["id"] for run in first}
        self.assertTrue(all(run["parent_run_id"] is None or run["parent_run_id"] in ids for run in first))
        self.assertEqual(trace_upload.build_live_traces("quality", 5)[1], 2)
        self.assertEqual(self.server.calls, [])

    def test_an_unknown_kind_is_a_clear_error(self):
        self.destination()
        with self.assertRaisesRegex(ValueError, "Use 'quality' or 'errors'"):
            trace_upload.send_live_traces("latency", 3)
        self.assertEqual(self.server.of("batch"), [])

    def test_calling_before_resolve_destination_is_a_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "resolve_destination"):
            trace_upload.send_live_traces("quality", 4)
        with self.assertRaisesRegex(RuntimeError, "resolve_destination"):
            trace_upload.live_scores()

    def test_a_refused_batch_prints_one_line_and_returns_zero(self):
        self.destination()
        self.server.refuse["batch"] = 403
        with self.assertNoLogs("langsmith", level="WARNING"):
            sent, printed = said(trace_upload.send_live_traces, "quality", 4)
        self.assertEqual(sent, 0)
        self.assertRegex(printed, r"^⏭️  Sending fresh traces failed \(\w+\)\. Continuing in local mode\.\n$")

    def test_without_a_key_nothing_is_sent(self):
        self.destination(False)
        self.assertEqual(said(trace_upload.send_live_traces, "quality", 4)[0], 0)
        self.assertEqual(self.server.calls, [])

    def test_scores_are_read_back_without_waiting(self):
        self.server.project_exists = True
        destination = self.destination()
        scored = {"wrong_return_window": {"n": 1, "avg": 1.0}}
        self.server.live_items = [{"id": str(uuid.uuid4()), "feedback_stats": scored if i < 2 else {}} for i in range(4)]
        self.server.calls.clear()
        asked = datetime.now(timezone.utc)
        result, printed = said(trace_upload.live_scores, destination)
        self.assertEqual(result, (2, 4))
        self.assertTrue(printed.startswith("2 of 4 scored so far (wrong_return_window on the fresh traces of the last 60 minutes)."), printed)
        self.assertEqual(printed.count("\n"), 1)
        body = self.server.of("query")[0].body
        self.assertEqual(body["filter"], 'has(tags, "live:m7")')
        self.assertEqual((body["project_ids"], body["is_root"], body["selects"]), ([PROJECT_ID], True, ["ID", "FEEDBACK_STATS"]))
        self.assertLess(abs((asked - timedelta(minutes=60) - datetime.fromisoformat(body["min_start_time"])).total_seconds()), 30)
        self.assert_every_query_names_a_start_time()

    def test_reading_scores_never_raises(self):
        self.server.project_exists = True
        destination = self.destination()
        self.server.refuse["query"] = 403
        with self.assertNoLogs("langsmith", level="WARNING"):
            result, printed = said(trace_upload.live_scores, destination)
        self.assertEqual(result, (0, 0))
        self.assertRegex(printed, r"^⏭️  Reading the scores back failed \(\w+\)\. Continuing in local mode\.\n$")


class QueueTest(KeyedTestCase):
    def test_a_new_queue_gets_the_eleven_flagged_runs(self):
        destination = self.uploaded()
        sent, printed = said(trace_upload.send_to_queue, destination, WRONG_KEYS)
        self.assertEqual(sent, 11)
        self.assertEqual(printed, "Queue techhub-deep-agent-return-window-review: 11 items sent. Open Annotation Queues to see them.\n")
        self.assertEqual(self.server.of("queues")[0].query["name"], ["techhub-deep-agent-return-window-review"])
        created = self.server.of("queue_create")[0].body
        self.assertEqual(created["name"], "techhub-deep-agent-return-window-review")
        self.assertTrue(created["description"] and created["rubric_instructions"])
        added = self.server.of("queue_items")
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].path, f"/api/v1/platform/annotation-queues/{QUEUE_ID}/items")
        self.assertEqual(added[0].query.get("extend_trace_retention"), ["false"])
        items = added[0].body["items"]
        self.assertEqual(sorted(item["run_id"] for item in items), sorted(destination.uploaded[key]["run_id"] for key in WRONG_KEYS))
        for item in items:
            self.assertEqual(set(item), {"item_type", "run_id", "project_id", "start_time"})
            self.assertEqual((item["item_type"], item["project_id"]), ("RUN", PROJECT_ID))
        self.assert_nothing_creates_or_deletes_a_project()

    def test_an_existing_queue_is_left_alone(self):
        destination = self.uploaded()
        self.server.queue_exists = True
        sent, printed = said(trace_upload.send_to_queue, destination, WRONG_KEYS)
        self.assertEqual(sent, 0)
        self.assertIn("already exists: nothing was added", printed)
        self.assertEqual(self.server.of("queue_create", "queue_items"), [])
        # This process did not fill it, so it cannot know that it is full: the line says what to do if it is empty.
        self.assertEqual(printed.count("\n"), 1)
        self.assertIn("If it is empty, an earlier run stopped before filling it: delete the queue there and run this again, or pass another name=.", printed)

    def test_a_queue_that_could_not_be_filled_is_filled_by_the_next_call(self):
        # Before: the queue was created, adding the items failed, and every later call found the
        # queue, said "already exists: nothing was added" and left it empty for good.
        destination = self.uploaded()
        self.server.refuse["queue_items"] = 500
        sent, printed = said(trace_upload.send_to_queue, destination, WRONG_KEYS)
        self.assertEqual(sent, 0)
        self.assertRegex(printed, r"^⏭️  Filling the queue failed \(\w+\)\. Continuing in local mode\.\n$")
        self.assertEqual(destination.queues_open, {"techhub-deep-agent-return-window-review": QUEUE_ID})

        self.server.refuse.clear()
        self.server.calls.clear()
        sent, printed = said(trace_upload.send_to_queue, destination, WRONG_KEYS)
        self.assertEqual(sent, 11)
        self.assertEqual(printed, "Queue techhub-deep-agent-return-window-review: 11 items sent. Open Annotation Queues to see them.\n")
        self.assertEqual(self.server.of("queue_create"), [], "the queue exists: it is filled, not created a second time")
        added = self.server.of("queue_items")
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].path, f"/api/v1/platform/annotation-queues/{QUEUE_ID}/items")
        self.assertEqual(sorted(item["run_id"] for item in added[0].body["items"]), sorted(destination.uploaded[key]["run_id"] for key in WRONG_KEYS))
        self.assertEqual(destination.queues_open, {})

        self.server.calls.clear()
        sent, printed = said(trace_upload.send_to_queue, destination, WRONG_KEYS)
        self.assertEqual(sent, 0)
        self.assertEqual(printed, "Queue techhub-deep-agent-return-window-review already exists: nothing was added. Open Annotation Queues to see it.\n")
        self.assertEqual(self.server.of("queue_create", "queue_items"), [], "a filled queue is never filled twice")

    def test_after_a_restart_an_unfilled_queue_gets_a_line_that_says_how_to_recover(self):
        first = self.uploaded()
        self.server.refuse["queue_items"] = 500
        said(trace_upload.send_to_queue, first, WRONG_KEYS)
        self.server.refuse.clear()
        fresh = self.destination()  # a new process remembers neither the upload nor the queue
        fresh.uploaded = dict(first.uploaded)
        self.server.calls.clear()
        sent, printed = said(trace_upload.send_to_queue, fresh, WRONG_KEYS)
        self.assertEqual(sent, 0)
        self.assertEqual(self.server.of("queue_create", "queue_items"), [])
        self.assertIn("If it is empty, an earlier run stopped before filling it", printed)
        self.assertEqual(said(trace_upload.send_to_queue, fresh, WRONG_KEYS, name="techhub-review-second-try")[0], 11, "another name= is the documented way out")

    def test_a_refusal_prints_one_line(self):
        destination = self.uploaded()
        self.server.refuse["queue_items"] = 403
        with self.assertNoLogs("langsmith", level="WARNING"):
            sent, printed = said(trace_upload.send_to_queue, destination, WRONG_KEYS)
        self.assertEqual(sent, 0)
        self.assertRegex(printed, r"^⏭️  Filling the queue failed \(\w+\)\. Continuing in local mode\.\n$")

    def test_without_a_key_nothing_is_sent(self):
        self.assertEqual(said(trace_upload.send_to_queue, self.destination(False), WRONG_KEYS)[0], 0)
        self.assertEqual(self.server.calls, [])


class SdkNamesTest(unittest.TestCase):
    """SDK names these helpers use beyond the ones `tests/test_module7_sdk_surface.py` lists.

    Several SDK methods end in `**kwargs` and would swallow a renamed keyword without an error, so
    each keyword is looked up in the signature.
    """

    def assert_named(self, function, *names):
        parameters = inspect.signature(function).parameters
        missing = [name for name in names if name not in parameters]
        self.assertFalse(missing, f"{function.__qualname__} (langsmith {langsmith.__version__}) no longer names {missing}")

    def test_client_settings(self):
        self.assert_named(Client.__init__, "api_url", "api_key", "timeout_ms", "auto_batch_tracing", "omit_traced_runtime_info",
                          "hide_inputs", "hide_outputs", "hide_metadata", "tracing_sampling_rate", "tracing_error_callback", "workspace_id")

    def test_methods(self):
        self.assert_named(Client.create_feedback, "run_id", "trace_id", "key", "score", "session_id", "start_time", "extend_trace_retention", "stop_after_attempt")
        self.assert_named(Client.list_projects, "limit")
        self.assert_named(Client.read_project, "project_name")
        client, _ = offline_client()
        self.assert_named(client.annotation_queues.items.create, "queue_id", "items", "extend_trace_retention")
        self.assert_named(client.agents.retrieve, "agent_id")
        self.assert_named(client.agents.create, "id", "name", "source_type")

    def test_run_fields_read_back(self):
        self.assertLessEqual({"ID", "TRACE_ID", "START_TIME", "METADATA", "FEEDBACK_STATS"}, set(typing.get_args(RunSelectField)))
        self.assertLessEqual({"id", "trace_id", "start_time", "metadata", "feedback_stats"}, set(Run.model_fields))

    def test_error_classes_and_the_environment_cache(self):
        self.assertTrue(issubclass(langsmith.NotFoundError, Exception))  # raised by client.agents.retrieve for a missing agent
        self.assertTrue(issubclass(ls_utils.LangSmithNotFoundError, ls_utils.LangSmithError))  # raised by read_project
        self.assertTrue(callable(getattr(ls_utils.get_env_var, "cache_clear", None)))

    def test_the_error_for_an_organization_scoped_key_is_still_recognisable(self):
        # The key-entry script tells this error from a rejected key by its class and by words in its text.
        self.assertTrue(issubclass(ls_utils.LangSmithUserError, ls_utils.LangSmithError))
        source = inspect.getsource(langsmith.client)
        self.assertIn("org_scoped_key_requires_workspace", source, f"langsmith {langsmith.__version__} no longer names this error code")
        self.assertRegex(source, rf"LangSmithUserError\(\s*\"[^\"]*{re.escape(connect.ORG_SCOPED_WORDS)}")
        self.assertIn("LANGSMITH_WORKSPACE_ID", source)


class SeedCommandTest(KeyedTestCase):
    """`scripts/module7_seed.py upload`."""

    def setUp(self):
        super().setUp()
        # The command loads `.env` from the repo root; a developer's own file must not steer the test.
        patcher = mock.patch("dotenv.load_dotenv", lambda *args, **kwargs: False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("LANGSMITH_API_KEY", None)

    def test_dry_run_prints_the_counts_and_makes_no_request(self):
        code, printed = said(seed_cli.main, ["upload", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(self.server.client_settings, [], "a dry run must not even build a client")
        self.assertIn("batch calls:    28", printed)
        self.assertIn("feedback calls: 170", printed)

    def test_dry_run_names_another_project(self):
        _, printed = said(seed_cli.main, ["upload", "--dry-run", "--project", "my-own-project"])
        self.assertIn("Tracing > project 'my-own-project'", printed)

    def test_without_a_key_nothing_is_sent(self):
        for value in (None, "<langsmith-api-key>"):
            with self.subTest(value=value):
                if value:
                    os.environ["LANGSMITH_API_KEY"] = value
                code, printed = said(seed_cli.main, ["upload"])
                self.assertEqual(code, 1)
                self.assertIn("nothing was sent", printed)
                self.assertEqual(self.server.calls, [])

    def test_with_a_key_the_seeded_day_is_uploaded(self):
        os.environ["LANGSMITH_API_KEY"] = FAKE_KEY
        code, printed = said(seed_cli.main, ["upload", "--project", "my-own-project"])
        self.assertEqual(code, 0)
        self.assertEqual({run["session_name"] for run in self.posted()}, {"my-own-project"})
        self.assertEqual(len(self.server.of("feedback")), 170)
        self.assertIn("In LangSmith, open Tracing, then the tracing project 'my-own-project'.", printed)
        self.assertNotIn(FAKE_KEY, printed)

    def test_a_failed_upload_exits_with_code_1(self):
        os.environ["LANGSMITH_API_KEY"] = FAKE_KEY
        self.server.refuse["batch"] = 403
        code, _ = said(seed_cli.main, ["upload"])
        self.assertEqual(code, 1)


class ConnectScriptTest(KeyedTestCase):
    """`scripts/module7_connect_langsmith.py`: the key-entry step of the hands-on track."""

    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.state_path, self.env_path = self.folder / "state.json", self.folder / ".env"
        self.asked: list[str] = []
        self.prompted: list[str] = []  # every time the hidden prompt was shown
        self.before_prompt: list[str] = []  # what had been printed each time the hidden prompt was shown

    def run_script(self, *flags, typed="", endpoint_answer=""):
        """Run the script with a stand-in for the hidden prompt. Returns `(exit code, everything it printed)`."""

        def ask(question):
            self.asked.append(question)
            return endpoint_answer

        def hidden_prompt(text):
            self.prompted.append(text)
            self.before_prompt.append(out.getvalue())
            return typed

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = connect.main(["--state", str(self.state_path), "--env", str(self.env_path), *flags], prompt=hidden_prompt, ask=ask)
        return code, out.getvalue() + err.getvalue()

    def state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def test_skip_writes_the_state_and_makes_no_request(self):
        code, printed = self.run_script("--skip")
        self.assertEqual(code, 0)
        state = self.state()
        self.assertEqual((state["langsmith"], state["reason"], state["seed_verified"], state["seeded"]), ("skipped", "--skip", True, False))
        self.assertEqual(state["seed_sha256"], hashlib.sha256((ts.DATA / ts.SEED_FILE).read_bytes()).hexdigest())
        self.assertEqual(set(state), {"langsmith", "reason", "seed_verified", "seed_sha256", "endpoint", "region", "seeded", "project", "where", "updated_at"})
        self.assertEqual(self.server.calls, [])
        self.assertEqual(self.server.client_settings, [])
        self.assertFalse(self.env_path.exists(), "--skip must not write .env")
        self.assertIn("Continuing without a LangSmith key", printed)

    def test_enter_at_the_prompt_means_no_key(self):
        code, _ = self.run_script(typed="   ")
        self.assertEqual(code, 0)
        self.assertEqual((self.state()["langsmith"], self.state()["reason"]), ("skipped", "no key entered"))
        self.assertEqual(self.server.calls, [])
        self.assertFalse(self.env_path.exists())

    def test_a_key_is_checked_stored_and_the_seed_uploaded(self):
        self.env_path.write_text('WORKSHOP_MODEL="anthropic:claude-haiku-4-5"\n# LANGSMITH_API_KEY="<langsmith-api-key>"\nLANGSMITH_ENDPOINT="<langsmith-endpoint>"\n', encoding="utf-8")
        self.server.accepting_hosts = {"eu.api.smith.langchain.com"}
        code, printed = self.run_script(typed=f"  {FAKE_KEY}\n")
        self.assertEqual(code, 0)

        # The region is found by asking each one; only the accepting one is used afterwards.
        probes = [call for call in self.server.calls if call.route == "project" and "name" not in call.query]
        self.assertEqual([call.host for call in probes], ["api.smith.langchain.com", "eu.api.smith.langchain.com"])
        self.assertEqual(self.asked, [])

        lines = self.env_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [
            'WORKSHOP_MODEL="anthropic:claude-haiku-4-5"',
            '# LANGSMITH_API_KEY="<langsmith-api-key>"',
            f"LANGSMITH_API_KEY={FAKE_KEY}",
            "LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com",
            "LANGSMITH_TRACING=true",
        ])
        self.assertEqual(stat.S_IMODE(self.env_path.stat().st_mode), 0o600)

        state = self.state()
        self.assertEqual((state["langsmith"], state["reason"], state["seed_verified"], state["seeded"]), ("verified", "key accepted", True, True))
        self.assertEqual((state["region"], state["endpoint"]), ("GCP EU", "https://eu.api.smith.langchain.com"))
        self.assertEqual(state["project"], "techhub-deep-agent-production")
        self.assertEqual(state["where"], "Tracing > project 'techhub-deep-agent-production'")
        self.assertEqual(len(self.posted()), len(SEED["runs"]))
        self.assertEqual(len(self.server.of("feedback")), 170)
        self.assertEqual({call.host for call in self.server.of("batch", "feedback")}, {"eu.api.smith.langchain.com"})
        self.assertIn("In LangSmith, open Tracing, then the tracing project 'techhub-deep-agent-production'.", printed)
        # Printed by a script, the sentence names a command to run again, not a notebook cell.
        self.assertIn("set TECHHUB_AGENT_ID in .env and run `uv run python scripts/module7_connect_langsmith.py --use-env-key` again.", printed)
        self.assertNotIn("Setup cell", printed)

        # The key is on disk in .env and nowhere else.
        self.assertNotIn(FAKE_KEY, printed)
        self.assertNotIn(FAKE_KEY, self.state_path.read_text(encoding="utf-8"))
        self.assert_nothing_creates_or_deletes_a_project()

    def test_no_upload_stores_the_key_only(self):
        code, _ = self.run_script("--no-upload", typed=FAKE_KEY)
        self.assertEqual(code, 0)
        self.assertEqual((self.state()["langsmith"], self.state()["seeded"]), ("verified", False))
        self.assertEqual(self.server.of("batch", "feedback"), [])

    def test_a_key_no_region_accepts_is_not_stored(self):
        self.server.accepting_hosts = set()
        code, printed = self.run_script(typed=FAKE_KEY)
        self.assertEqual(code, 0, "a key is never required")
        self.assertEqual((self.state()["langsmith"], self.state()["reason"]), ("skipped", "key rejected"))
        self.assertEqual(sorted({call.host for call in self.server.calls}), sorted(urlsplit(address).netloc for _, address in connect.REGIONS))
        self.assertEqual(len(self.asked), 1, "the script asks once for a self-hosted address")
        self.assertFalse(self.env_path.exists())
        self.assertEqual(self.server.of("batch", "feedback"), [])
        self.assertNotIn(FAKE_KEY, printed)
        self.assertNotIn("LANGSMITH_API_KEY", os.environ)

    def test_a_self_hosted_address_can_be_typed(self):
        self.server.accepting_hosts = {"langsmith.invalid"}
        code, _ = self.run_script("--no-upload", typed=FAKE_KEY, endpoint_answer="https://langsmith.invalid/api/v1/")
        self.assertEqual(code, 0)
        self.assertEqual((self.state()["region"], self.state()["endpoint"]), ("custom", "https://langsmith.invalid/api/v1"))
        self.assertIn("LANGSMITH_ENDPOINT=https://langsmith.invalid/api/v1", self.env_path.read_text(encoding="utf-8"))

    def test_the_endpoint_flag_skips_the_region_check(self):
        self.server.accepting_hosts = {"langsmith.invalid"}
        code, _ = self.run_script("--no-upload", "--endpoint", "https://langsmith.invalid/api/v1", typed=FAKE_KEY)
        self.assertEqual(code, 0)
        self.assertEqual({call.host for call in self.server.calls}, {"langsmith.invalid"})
        self.assertEqual(self.state()["langsmith"], "verified")

    def test_enter_with_a_key_already_in_env_sends_nothing(self):
        # The prompt says "press Enter to continue without a key". Before, Enter took the key from .env (every
        # attendee of Modules 1 to 6 has one there), probed the regions with it and uploaded the seeded day.
        text = f'WORKSHOP_MODEL="anthropic:claude-haiku-4-5"\nLANGSMITH_API_KEY="{FAKE_KEY}"\nLANGSMITH_ENDPOINT="https://eu.api.smith.langchain.com"\n'
        for flags in ((), ("--no-upload",)):
            with self.subTest(flags=flags):
                self.env_path.write_text(text, encoding="utf-8")
                code, printed = self.run_script(*flags, typed="")
                self.assertEqual(code, 0)
                self.assertEqual(self.server.calls, [], "Enter must not make a network call")
                self.assertEqual(self.server.client_settings, [], "Enter must not even build a client")
                self.assertEqual(self.env_path.read_text(encoding="utf-8"), text, "Enter must not rewrite .env")
                state = self.state()
                self.assertEqual((state["langsmith"], state["reason"], state["seeded"], state["endpoint"]), ("skipped", "no key entered", False, None))
                self.assertIn("already holds a LangSmith key: it was not used and not changed", printed)
                self.assertIn("--use-env-key", printed)
                self.assertIn("Continuing without a LangSmith key", printed)
                self.assertNotIn(FAKE_KEY, printed)
                self.assertNotIn("LANGSMITH_API_KEY", os.environ)
        self.assertIn("press Enter to continue without a key", connect.PROMPT)

    def test_use_env_key_checks_the_stored_key_and_uploads_without_asking(self):
        self.env_path.write_text(f'LANGSMITH_API_KEY="{FAKE_KEY}"\n', encoding="utf-8")
        code, printed = self.run_script("--use-env-key")
        self.assertEqual(code, 0)
        self.assertEqual(self.prompted, [], "--use-env-key must not show the prompt")
        state = self.state()
        self.assertEqual((state["langsmith"], state["reason"], state["seeded"]), ("verified", "key accepted", True))
        self.assertEqual(len(self.posted()), len(SEED["runs"]))
        self.assertEqual(len(self.server.of("feedback")), 170)
        self.assertEqual(self.env_path.read_text(encoding="utf-8").count("LANGSMITH_API_KEY="), 1)
        self.assertIn(f"LANGSMITH_API_KEY={FAKE_KEY}", self.env_path.read_text(encoding="utf-8"))
        self.assertIn("Using the LangSmith key that is already in .env.", printed)
        self.assertNotIn(FAKE_KEY, printed)

    def test_use_env_key_with_no_upload_and_with_no_key_in_env(self):
        self.env_path.write_text(f'LANGSMITH_API_KEY="{FAKE_KEY}"\n', encoding="utf-8")
        code, _ = self.run_script("--use-env-key", "--no-upload")
        self.assertEqual(code, 0)
        self.assertEqual((self.state()["langsmith"], self.state()["seeded"]), ("verified", False))
        self.assertEqual(self.server.of("batch", "feedback"), [])

        self.server.calls.clear()
        self.env_path.write_text('# LANGSMITH_API_KEY=""\nLANGSMITH_API_KEY="<langsmith-api-key>"\n', encoding="utf-8")
        code, printed = self.run_script("--use-env-key")
        self.assertEqual(code, 0, "a key is never required")
        self.assertEqual((self.state()["langsmith"], self.state()["reason"]), ("skipped", "no key entered"))
        self.assertIn("holds no LangSmith key", printed)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(self.prompted, [])

    def test_use_env_key_never_asks_a_question(self):
        text = f'LANGSMITH_API_KEY="{FAKE_KEY}"\n'
        self.env_path.write_text(text, encoding="utf-8")
        self.server.accepting_hosts = set()  # no region accepts the stored key
        code, printed = self.run_script("--use-env-key", endpoint_answer="https://langsmith.invalid/api/v1")
        self.assertEqual(code, 0, "a key is never required")
        self.assertEqual((self.prompted, self.asked), ([], []), "--use-env-key must run without a terminal")
        self.assertEqual((self.state()["langsmith"], self.state()["reason"]), ("skipped", "key rejected"))
        self.assertEqual(self.env_path.read_text(encoding="utf-8"), text)
        self.assertIn("--endpoint", printed)
        self.assertEqual(self.server.of("batch", "feedback"), [])
        self.assertNotIn(FAKE_KEY, printed)

    def test_the_modes_cannot_be_combined(self):
        for flags in (("--skip", "--use-env-key"), ("--check", "--skip"), ("--send-live", "--use-env-key")):
            with self.subTest(flags=flags), self.assertRaises(SystemExit) as stopped:
                self.run_script(*flags)
            self.assertEqual(stopped.exception.code, 2)
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.server.calls, [])

    def test_what_a_key_will_do_is_printed_where_the_choice_is_made(self):
        code, printed = self.run_script(typed="")
        self.assertEqual(self.prompted, [connect.PROMPT])
        self.assertIn("uploads the seeded day of synthetic traces to that key's workspace", printed)
        self.assertIn("--no-upload", printed)
        self.assertNotIn("uploads the seeded day", self.run_script("--no-upload", typed="")[1])
        self.assertNotIn("uploads the seeded day", self.run_script("--skip")[1])

    def test_an_agent_based_workspace_is_explained_before_the_key_is_asked_for(self):
        # New LangSmith Cloud organizations are agent-based, and an upload under a bare project name is not documented
        # there. The only test the documentation gives is what the top-left control shows, so it is said before the upload.
        code, _ = self.run_script(typed=FAKE_KEY)
        self.assertEqual(code, 0)
        said_first = self.before_prompt[0]
        for words in ("Where the upload goes: the tracing project 'techhub-deep-agent-production'", "control at the top left of LangSmith",
                      "the LangSmith logo", "your workspace name", "agent-based", "is not documented", "Press Enter now",
                      "TECHHUB_AGENT_ID=<agent id> to .env", "--no-upload"):
            self.assertIn(words, said_first)
        self.assertEqual(self.server.of("agent", "agent_create"), [], "no request is made to find out the kind of workspace")

        # Nothing is uploaded with --no-upload or --skip, so neither prints it.
        self.before_prompt.clear()
        self.run_script("--no-upload", typed="")
        self.assertNotIn("TECHHUB_AGENT_ID", self.before_prompt[0])
        self.assertNotIn("Where the upload goes", self.run_script("--skip")[1])

        # Another project name is the one that is named.
        self.before_prompt.clear()
        self.env_path.write_text('M7_PROJECT="my-own-project"\n', encoding="utf-8")
        self.run_script(typed="")
        self.assertIn("the tracing project 'my-own-project'", self.before_prompt[0])

        # With the agent already named in .env, the notice says where the traces go and does not ask the learner to set it.
        self.before_prompt.clear()
        self.server.calls.clear()
        self.env_path.write_text(f'TECHHUB_AGENT_ID="{AGENT_ID}"\n', encoding="utf-8")
        self.run_script(typed="")
        self.assertIn(f"the Production environment of the agent '{AGENT_ID}'", self.before_prompt[0])
        self.assertNotIn("Press Enter now", self.before_prompt[0])
        self.assertEqual(self.server.calls, [], "Enter still sends nothing")

    def test_with_the_agent_named_in_env_the_upload_goes_to_the_agent(self):
        # What the notice asks for: TECHHUB_AGENT_ID in .env, then the script again.
        self.server.agent = agent_reply()
        self.env_path.write_text(f'LANGSMITH_API_KEY="{FAKE_KEY}"\nTECHHUB_AGENT_ID="{AGENT_ID}"\n', encoding="utf-8")
        code, printed = self.run_script("--use-env-key")
        self.assertEqual(code, 0)
        self.assertEqual({run["session_name"] for run in self.posted()}, {AGENT_PROJECT_NAME})
        self.assertEqual((self.state()["seeded"], self.state()["project"]), (True, AGENT_PROJECT_NAME))
        self.assertIn("select the agent 'TechHub support' in the agent switcher", printed)
        self.assert_nothing_creates_or_deletes_a_project()

    def test_a_workspace_id_in_env_is_sent_when_the_key_is_checked(self):
        # An organization-scoped key is accepted only together with a workspace id (the X-Tenant-Id header). The script
        # loaded .env only after a region had accepted the key, so the check went without the id and the key was "rejected".
        self.server.workspace_required = WORKSPACE_ID
        text = f'LANGSMITH_API_KEY="{FAKE_KEY}"\nLANGSMITH_WORKSPACE_ID="{WORKSPACE_ID}"\n'
        self.env_path.write_text(text, encoding="utf-8")
        code, printed = self.run_script("--use-env-key")
        self.assertEqual(code, 0)
        state = self.state()
        self.assertEqual((state["langsmith"], state["reason"], state["seeded"]), ("verified", "key accepted", True), printed)
        probes = [call for call in self.server.calls if call.route == "project" and "name" not in call.query]
        self.assertEqual([(call.host, call.tenant) for call in probes], [("api.smith.langchain.com", WORKSPACE_ID)])
        self.assertEqual({call.tenant for call in self.server.of("batch", "feedback")}, {WORKSPACE_ID}, "the upload names the workspace too")
        self.assertIn(f'LANGSMITH_WORKSPACE_ID="{WORKSPACE_ID}"', self.env_path.read_text(encoding="utf-8"), "the line in .env is kept")

        # The same for a key typed at the prompt, and for an id that is set in the environment instead of .env.
        self.server.calls.clear()
        self.env_path.write_text(f'LANGSMITH_WORKSPACE_ID={WORKSPACE_ID}  # my workspace\n', encoding="utf-8")
        code, _ = self.run_script("--no-upload", typed=FAKE_KEY)
        self.assertEqual((code, self.state()["langsmith"]), (0, "verified"))
        self.env_path.unlink()
        os.environ.pop("LANGSMITH_WORKSPACE_ID", None)  # the run above loaded .env into this process
        os.environ["LANGSMITH_WORKSPACE_ID"] = WORKSPACE_ID
        code, _ = self.run_script("--no-upload", typed=FAKE_KEY)
        self.assertEqual((code, self.state()["langsmith"]), (0, "verified"))

    def test_an_organization_scoped_key_without_a_workspace_id_is_named_as_such(self):
        self.server.workspace_required = WORKSPACE_ID
        code, printed = self.run_script(typed=FAKE_KEY)
        self.assertEqual(code, 0, "a key is never required")
        state = self.state()
        self.assertEqual((state["langsmith"], state["reason"], state["seeded"], state["endpoint"]), ("skipped", "workspace id needed", False, None))
        self.assertIn("organization-scoped key", printed)
        self.assertIn("Add the line LANGSMITH_WORKSPACE_ID=<your workspace id> to .env (the id of a workspace, not of the organization), then run this script again.", printed)
        self.assertNotIn("keys start with lsv2_", printed, "the key is not malformed, and saying so sends the learner the wrong way")
        self.assertNotIn("No LangSmith address accepted it", printed)
        self.assertEqual([call.host for call in self.server.calls], ["api.smith.langchain.com"], "the region that knows the key ends the search")
        self.assertEqual(self.asked, [], "no question about a self-hosted address")
        self.assertFalse(self.env_path.exists(), "nothing is saved")
        self.assertEqual(self.server.of("batch", "feedback"), [])
        self.assertNotIn(FAKE_KEY, printed)
        self.assertNotIn("LANGSMITH_API_KEY", os.environ)

        # With --use-env-key the advice names that form of the command.
        self.env_path.write_text(f'LANGSMITH_API_KEY="{FAKE_KEY}"\n', encoding="utf-8")
        code, printed = self.run_script("--use-env-key")
        self.assertEqual((code, self.state()["reason"]), (0, "workspace id needed"))
        self.assertIn("then run this script again with --use-env-key.", printed)

        # An id that LangSmith does not accept: the key is reported as rejected, and the id is named as a thing to check.
        self.env_path.write_text('LANGSMITH_WORKSPACE_ID="77777777-7777-4777-8777-777777777777"\n', encoding="utf-8")
        code, printed = self.run_script(typed=FAKE_KEY)
        self.assertEqual((code, self.state()["reason"]), (0, "key rejected"))
        self.assertIn("A LANGSMITH_WORKSPACE_ID was sent with the key.", printed)
        self.assertNotIn("77777777", printed)

    def test_the_probe_tells_three_answers_apart(self):
        self.assertEqual(connect.probe("https://api.smith.langchain.com", FAKE_KEY), connect.ACCEPTED)
        self.server.workspace_required = WORKSPACE_ID
        self.assertEqual(connect.probe("https://api.smith.langchain.com", FAKE_KEY), connect.NEEDS_WORKSPACE)
        self.assertEqual(connect.probe("https://api.smith.langchain.com", FAKE_KEY, WORKSPACE_ID), connect.ACCEPTED)
        self.assertEqual(connect.probe("https://api.smith.langchain.com", FAKE_KEY, "another-id"), connect.REJECTED)
        self.server.workspace_required, self.server.accepting_hosts = None, set()
        self.assertEqual(connect.probe("https://api.smith.langchain.com", FAKE_KEY), connect.REJECTED)
        self.assertNotIn("workspace_id", self.server.client_settings[0], "no workspace id is passed when none is set")

    def test_send_live_sends_four_fresh_traces_with_the_key_in_env(self):
        text = f'LANGSMITH_API_KEY="{FAKE_KEY}"\nLANGSMITH_ENDPOINT="https://eu.api.smith.langchain.com"\n'
        self.env_path.write_text(text, encoding="utf-8")
        self.server.project_exists = True
        code, printed = self.run_script("--send-live")
        self.assertEqual(code, 0)
        self.assertEqual(self.prompted, [], "--send-live must not show the prompt")
        roots = [run for run in self.posted() if run["parent_run_id"] is None]
        self.assertEqual(len(roots), 4)
        ends = {run["id"]: run for run in self.patched()}
        self.assertEqual(sum(1 for run in roots if perform_eval({**run, **ends[run["id"]]})["wrong_return_window"]), 2)
        for run in roots:
            self.assertEqual((run["tags"], run["name"], run["session_name"]), (["live:m7"], "deep_support_agent", "techhub-deep-agent-production"))
        self.assertEqual({call.host for call in self.server.calls}, {"eu.api.smith.langchain.com"}, "the address in .env is the one used")
        self.assertEqual(self.server.of("feedback"), [], "the evaluator in LangSmith writes the scores, not this script")
        self.assertIn("Sent 4 fresh traces (2 give the wrong window).", printed)
        self.assertIn("Find them under: Tracing > project 'techhub-deep-agent-production'", printed)
        self.assertIn("is not documented", printed)
        self.assertFalse(self.state_path.exists(), "--send-live must not write the state file")
        self.assertEqual(self.env_path.read_text(encoding="utf-8"), text)
        self.assertNotIn(FAKE_KEY, printed)
        self.assert_nothing_creates_or_deletes_a_project()

    def test_send_live_without_a_key_or_with_a_refusal_sends_nothing_and_exits_1(self):
        self.env_path.write_text('# LANGSMITH_API_KEY=""\n', encoding="utf-8")
        code, printed = self.run_script("--send-live")
        self.assertEqual(code, 1)
        self.assertEqual(self.server.calls, [])
        self.assertIn("holds no LangSmith key", printed)
        self.assertIn("without one, carry on", printed)

        self.env_path.write_text(f'LANGSMITH_API_KEY="{FAKE_KEY}"\n', encoding="utf-8")
        self.server.refuse["batch"] = 403
        code, printed = self.run_script("--send-live")
        self.assertEqual(code, 1)
        self.assertIn("⏭️  Sending fresh traces failed", printed)
        self.assertNotIn("Find them under", printed)

    def test_an_address_already_in_env_is_tried_first(self):
        self.env_path.write_text(f'LANGSMITH_API_KEY="{FAKE_KEY}"\nLANGSMITH_ENDPOINT="https://langsmith.invalid/api/v1" # self-hosted\n', encoding="utf-8")
        self.server.accepting_hosts = {"langsmith.invalid"}
        code, _ = self.run_script("--use-env-key", "--no-upload")
        self.assertEqual(code, 0)
        self.assertEqual([call.host for call in self.server.calls if call.route == "project" and "name" not in call.query], ["langsmith.invalid"])
        self.assertEqual((self.state()["region"], self.state()["endpoint"]), ("custom", "https://langsmith.invalid/api/v1"))

    def test_skip_leaves_an_existing_env_file_alone(self):
        text = f'LANGSMITH_API_KEY="{FAKE_KEY}"\n'
        self.env_path.write_text(text, encoding="utf-8")
        code, printed = self.run_script("--skip")
        self.assertEqual(code, 0)
        self.assertEqual(self.env_path.read_text(encoding="utf-8"), text)
        self.assertEqual(self.server.calls, [])
        self.assertNotIn(FAKE_KEY, printed)

    def test_a_failed_upload_still_records_the_accepted_key(self):
        self.server.refuse["batch"] = 403
        code, printed = self.run_script(typed=FAKE_KEY)
        self.assertEqual(code, 0)
        self.assertEqual((self.state()["langsmith"], self.state()["seeded"]), ("verified", False))
        self.assertIn("⏭️  Upload failed", printed)

    def test_without_a_terminal_the_script_stops_before_asking(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("")), contextlib.redirect_stdout(out):
            code = connect.main(["--state", str(self.state_path), "--env", str(self.env_path)])
        self.assertEqual(code, 2)
        self.assertIn("pass --skip", out.getvalue())
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.server.calls, [])

    def test_a_seed_file_that_does_not_verify_is_reported(self):
        with mock.patch.object(connect, "verify_seed", lambda: (False, None)):
            code, printed = self.run_script("--skip")
        self.assertEqual(code, 1)
        self.assertIs(self.state()["seed_verified"], False)
        self.assertIn("differs from a fresh generation", printed)
        # The advice works in the hands-on sandbox too: one file, and not the command that prints the answer key.
        self.assertIn("`git checkout -- workshop_modules/module_7/data/techhub_production_day.json`", printed)
        # A command that regenerates the file works in every challenge of the track and where there is no git history.
        self.assertIn("run `uv run python workshop_modules/module_7/exercises/check.py --restore-data`", printed)
        self.assertNotIn("Skip on the Setup challenge", printed, "a learner who is past the Setup challenge cannot click its Skip")
        self.assertNotIn("module7_seed.py", printed)

    def test_check_passes_after_skip_and_after_a_key_and_fails_before(self):
        code, printed = self.run_script("--check")
        self.assertEqual(code, 1)
        self.assertRegex(printed, r"^FAIL: setup is not recorded yet\. Run `uv run python scripts/module7_connect_langsmith\.py` .*--skip.*\n$")
        self.assertFalse(self.state_path.exists(), "--check must not write the state file")

        self.run_script("--skip")
        before = self.state_path.read_text(encoding="utf-8")
        code, printed = self.run_script("--check")
        self.assertEqual((code, printed), (0, "PASS: setup is recorded (LangSmith: skipped) and the seed file is verified.\n"))
        self.assertEqual(self.state_path.read_text(encoding="utf-8"), before)

        self.run_script("--no-upload", typed=FAKE_KEY)
        self.server.calls.clear()
        code, printed = self.run_script("--check")
        self.assertEqual((code, printed), (0, "PASS: setup is recorded (LangSmith: verified) and the seed file is verified.\n"))
        self.assertEqual(self.server.calls, [], "--check must not contact LangSmith")

    def test_check_fails_when_the_seed_file_changed_or_the_state_is_not_one_of_the_two(self):
        self.run_script("--skip")
        with mock.patch.object(connect, "verify_seed", lambda: (True, "0" * 64)):  # another file than the one recorded
            code, printed = self.run_script("--check")
        self.assertEqual(code, 1)
        self.assertTrue(printed.startswith("FAIL: the seed file workshop_modules/module_7/data/techhub_production_day.json"))
        self.assertIn("`git checkout -- workshop_modules/module_7/data/techhub_production_day.json`", printed, "restore the one file, not the folder")
        self.assertNotRegex(printed, r"git checkout -- workshop_modules/module_7/data(?!/)")
        self.assertNotIn("module7_seed.py", printed)
        self.assertEqual(printed.count("\n"), 1)
        with mock.patch.object(connect, "verify_seed", lambda: (False, None)):
            self.assertEqual(self.run_script("--check")[0], 1)
        for content in ('{"langsmith": "pending", "seed_verified": true}', "not json", "[]"):
            with self.subTest(content=content):
                self.state_path.write_text(content, encoding="utf-8")
                code, printed = self.run_script("--check")
                self.assertEqual(code, 1)
                self.assertEqual(printed.count("\n"), 1)

    def test_no_print_call_mentions_the_variable_that_holds_the_key(self):
        tree = ast.parse((REPO_ROOT / "scripts" / "module7_connect_langsmith.py").read_text(encoding="utf-8"))
        prints = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"]
        self.assertGreater(len(prints), 5)
        for call in prints:
            names = {node.id for node in ast.walk(call) if isinstance(node, ast.Name)}
            self.assertFalse(names & {"secret", "settings", "typed"}, f"line {call.lineno} prints a variable that can hold the key")

    def test_the_default_paths_are_in_the_repo_root(self):
        self.assertEqual(connect.STATE_FILE, REPO_ROOT / ".m7_state.json")
        self.assertEqual(connect.ENV_FILE, REPO_ROOT / ".env")
        self.assertEqual(connect.REGIONS[0], ("GCP US", "https://api.smith.langchain.com"))
        self.assertEqual(OFFLINE_API_URL, "http://offline.invalid")


if __name__ == "__main__":
    unittest.main()
