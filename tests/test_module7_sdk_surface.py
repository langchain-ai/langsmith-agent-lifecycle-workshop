"""Module 7 calls these SDK names with these arguments; a package bump that renames one fails here.

Each test reads a signature (``inspect.signature``) or a generated type and compares it with the call
that Module 7 makes (the "Calls" columns of sections 7 to 10 in
``docs/2026-11-19-module-7-monitoring-governance-prd.md``). Nothing is sent: the one client is built
with a fixed ``info`` so it never asks a server for its version, no model is constructed, and every
socket connect and host-name lookup is refused and recorded.

Run: uv run python -m unittest tests.test_module7_sdk_surface
"""

import datetime as dt
import inspect
import os
import socket
import typing
import unittest
from importlib import metadata
from unittest import mock

import httpx
import langsmith
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langsmith import Client
from langsmith import utils as ls_utils
from langsmith.anonymizer import create_anonymizer
from langsmith.schemas import (
    InsightsCluster,
    InsightsHighlightedTrace,
    InsightsReportResult,
    InsightsSummaryReport,
)
from langsmith.types import RunSelectField, agent, agent_create_params
from langsmith.types.annotation_queues import item_create_params
from langsmith.types.issue import Issue
from langsmith.uuid import uuid7_from_datetime

NAMED = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
INSTALLED = ", ".join(f"{p} {metadata.version(p)}" for p in ("langsmith", "langchain", "langchain-openai"))

AN_ID = "00000000-0000-7000-8000-000000000000"
NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)
EMAIL = r"[\w.+-]+@[\w-]+\.[\w.-]+"

CLIENT = None
NETWORK = []  # every attempted connect or host-name lookup; must stay empty


def _refuse_connect(self, address, *args, **kwargs):
    NETWORK.append(("connect", address))
    raise OSError(f"this test must not open a connection (tried {address!r})")


def _refuse_lookup(host, *args, **kwargs):
    NETWORK.append(("lookup", host))
    raise socket.gaierror(f"this test must not look up a host name (tried {host!r})")


def setUpModule():
    global CLIENT
    guards = [mock.patch.object(socket.socket, "connect", _refuse_connect),
              mock.patch.object(socket.socket, "connect_ex", _refuse_connect),
              mock.patch.object(socket, "getaddrinfo", _refuse_lookup)]
    for patcher in guards:
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)
    # An empty environment, so a variable in the caller's shell cannot change the client.
    # The SDK keeps every environment lookup for the life of the process (`get_env_var` is an
    # `lru_cache`), so the lookups made in the empty environment are dropped again, here and when the
    # module ends: a test module that runs later in the same process must see its own environment.
    unittest.addModuleCleanup(ls_utils.get_env_var.cache_clear)
    with mock.patch.dict(os.environ, {}, clear=True):
        CLIENT = Client(api_key="not-a-real-key", api_url="https://offline.invalid", info={},
                        auto_batch_tracing=False)
        # `Client(...)` does not build the generated clients behind `client.runs`,
        # `client.annotation_queues` and `client.agents`: the first use of each attribute does, and the
        # HTTP client it creates then reads the proxy and certificate variables (ALL_PROXY,
        # SSL_CERT_FILE, …). They are built here and kept by the client, so that a proxy setting in
        # the caller's shell cannot fail a signature check.
        for resource in ("runs", "annotation_queues", "agents"):
            getattr(CLIENT, resource)
    ls_utils.get_env_var.cache_clear()


def literal_values(tp) -> set:
    """Every value of the ``Literal`` inside a type (through ``Required[...]`` and ``Annotated[...]``)."""
    if typing.get_origin(tp) is typing.Literal:
        return set(typing.get_args(tp))
    return set().union(*(literal_values(arg) for arg in typing.get_args(tp)), set())


class SurfaceTestCase(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(NETWORK, [], "a signature check tried to reach the network")

    def assert_call(self, func, *args, **kwargs):
        """The call binds to the signature, and every keyword is a parameter the SDK names.

        ``bind`` alone is not enough: a method that ends in ``**kwargs`` accepts any keyword, so a
        renamed parameter would be swallowed without an error.
        """
        label = f"{getattr(func, '__qualname__', func)} ({INSTALLED})"
        signature = inspect.signature(func)
        named = {name for name, p in signature.parameters.items() if p.kind in NAMED}
        gone = sorted(set(kwargs) - named)
        self.assertFalse(gone, f"{label} no longer names the parameter(s) {gone}; it has {sorted(named)}")
        try:
            signature.bind(*args, **kwargs)
        except TypeError as error:
            self.fail(f"{label} no longer accepts the call Module 7 makes: {error}")

    def assert_fields(self, model, *names):
        gone = sorted(set(names) - set(model.model_fields))
        self.assertFalse(gone, f"{model.__name__} ({INSTALLED}) no longer has the field(s) {gone}")


class ClientMethodsTest(SurfaceTestCase):
    """Methods of ``langsmith.Client`` (Section 1 upload, scores, queue and REST cells; Sections 2 and 3)."""

    def test_batch_ingest_runs_takes_create_and_update(self):
        self.assert_call(CLIENT.batch_ingest_runs, create=[{"id": AN_ID}])
        self.assert_call(CLIENT.batch_ingest_runs, update=[{"id": AN_ID}])

    def test_flush(self):
        self.assert_call(CLIENT.flush)

    def test_create_feedback_names_the_project_the_time_and_the_retention_switch(self):
        self.assert_call(CLIENT.create_feedback, run_id=AN_ID, trace_id=AN_ID, key="user_score", score=1,
                         session_id=AN_ID, start_time=NOW, extend_trace_retention=False)

    def test_read_project_by_name(self):
        self.assert_call(CLIENT.read_project, project_name="techhub-deep-agent-production")

    def test_create_annotation_queue(self):
        self.assert_call(CLIENT.create_annotation_queue, name="techhub-deep-agent-return-window-review",
                         description="d", rubric_instructions="r")

    def test_list_annotation_queues_by_name(self):
        self.assert_call(CLIENT.list_annotation_queues, name="techhub-deep-agent-return-window-review")

    def test_list_project_issues(self):
        # Module 7 passes the project name only. `priority` is pinned because the notebook and
        # CLAUDE.md warn against it by name (it is not a real filter); `status` is the real one.
        self.assert_call(CLIENT.list_project_issues, "techhub-deep-agent-production")
        self.assert_call(CLIENT.list_project_issues, project_name="p", status="open", priority="high")

    def test_get_insights_report(self):
        self.assert_call(CLIENT.get_insights_report, id=AN_ID, project_id=AN_ID, include_runs=False)

    def test_request_with_retries_takes_method_path_and_http_keywords(self):
        self.assert_call(CLIENT.request_with_retries, "GET", "/api/v2/runs/rules")
        # `json=` and `params=` are not named: they reach the HTTP session through **kwargs
        kinds = {p.kind for p in inspect.signature(CLIENT.request_with_retries).parameters.values()}
        self.assertIn(inspect.Parameter.VAR_KEYWORD, kinds)
        self.assert_call(CLIENT.request_with_retries, "POST", "/api/v1/runs/rules")

    def test_dataset_methods(self):
        self.assert_call(CLIENT.has_dataset, dataset_name="techhub-deep-agent-regressions")
        self.assert_call(CLIENT.create_dataset, dataset_name="techhub-deep-agent-regressions", description="d")
        example = {"inputs": {"question": "q"}, "outputs": {"answer": "a"}}
        self.assert_call(CLIENT.create_examples, dataset_name="techhub-deep-agent-regressions", examples=[example])
        self.assert_call(CLIENT.create_examples, dataset_id=AN_ID, examples=[example])

    def test_client_constructor(self):
        # Imported here, not at the top: a problem in utils/offline_capture.py then fails this one test
        # and leaves the other signature checks running.
        from utils.offline_capture import _offline_client_defaults

        # Client(anonymizer=…) is the masking client of Section 4.
        self.assert_call(Client, anonymizer=lambda payload: payload)
        # `offline_client()` builds its client as `Client(**{**_offline_client_defaults(), **client_kwargs})`.
        # The defaults are taken from the module, so every keyword it passes is checked: the address and
        # key, `auto_batch_tracing`, `info`, the three `hide_*` switches, `tracing_sampling_rate` and
        # `tracing_mode` (langsmith 0.14). Each one stops `Client` reading an environment variable, so a
        # renamed keyword must fail here and not be dropped.
        defaults = _offline_client_defaults()
        self.assertTrue(defaults, "utils.offline_capture._offline_client_defaults() returned no keywords to check")
        self.assert_call(Client, **defaults)
        # The module also builds `Client(auto_batch_tracing=False)` (utils/langsmith_links.py) and
        # `offline_client(hide_inputs=None)`, which passes `hide_inputs=None` on to `Client`.
        self.assert_call(Client, auto_batch_tracing=False)
        self.assert_call(Client, hide_inputs=None)


class GeneratedResourcesTest(SurfaceTestCase):
    """The generated resources on the client: ``client.runs``, ``client.annotation_queues``, ``client.agents``."""

    def test_runs_query_is_awaited_with_these_keywords(self):
        query = CLIENT.runs.query
        self.assert_call(query, project_ids=[AN_ID], is_root=True, filter='has(tags, "seed:m7")',
                         min_start_time=NOW, page_size=1, selects=["ID"])
        # Module 7 writes `await client.runs.query(...)`. Building the page object sends nothing.
        page = query(project_ids=[AN_ID], is_root=True, min_start_time=NOW, page_size=1, selects=["ID"])
        self.assertTrue(inspect.isawaitable(page), f"client.runs.query(...) is no longer awaitable ({INSTALLED})")
        if inspect.iscoroutine(page):
            page.close()

    def test_runs_query_select_fields(self):
        self.assertLessEqual({"ID", "FEEDBACK_STATS"}, literal_values(RunSelectField))

    def test_annotation_queue_items_create(self):
        create = CLIENT.annotation_queues.items.create
        item = {"item_type": "RUN", "run_id": AN_ID, "project_id": AN_ID, "start_time": NOW}
        self.assert_call(create, "queue-id", items=[item])
        self.assertTrue(inspect.iscoroutinefunction(create), "Module 7 awaits annotation_queues.items.create")
        hints = typing.get_type_hints(item_create_params.Item, include_extras=True)
        self.assertLessEqual(set(item), set(hints))
        self.assertIn("RUN", literal_values(hints["item_type"]))

    def test_agents_retrieve_and_create_are_plain_calls(self):
        self.assert_call(CLIENT.agents.retrieve, "techhub-support")
        self.assert_call(CLIENT.agents.create, id="techhub-support", source_type="EXTERNAL", name="TechHub support")
        for method in (CLIENT.agents.retrieve, CLIENT.agents.create):
            self.assertFalse(inspect.iscoroutinefunction(method), "Module 7 calls client.agents without await")
        hints = typing.get_type_hints(agent_create_params.AgentCreateParams, include_extras=True)
        self.assertIn("EXTERNAL", literal_values(hints["source_type"]))

    def test_agent_environment_carries_the_project_name(self):
        self.assert_fields(agent.Agent, "environments")
        self.assert_fields(agent.Environment, "environment", "tracer_session_name")
        self.assertIn("PRODUCTION", literal_values(agent.Environment.model_fields["environment"].annotation))


class ModuleLevelNamesTest(SurfaceTestCase):
    """Functions and types imported from ``langsmith`` and its submodules."""

    def test_uuid7_from_datetime(self):
        self.assert_call(uuid7_from_datetime, NOW)
        self.assertEqual(uuid7_from_datetime(NOW).version, 7)

    def test_create_anonymizer_takes_pattern_and_replace_rules(self):
        rules = [{"pattern": EMAIL, "replace": "<email>"}]
        self.assert_call(create_anonymizer, rules)
        masked = create_anonymizer(rules)({"messages": [{"content": "Write to pat@example.com"}], "control": "keep"})
        self.assertEqual(masked, {"messages": [{"content": "Write to <email>"}], "control": "keep"})

    def test_configure_can_switch_tracing_off(self):
        self.assert_call(langsmith.configure, enabled=False)

    def test_tracing_context_takes_enabled_and_client(self):
        self.assert_call(langsmith.tracing_context, enabled=True, client=CLIENT)

    def test_insights_report_result(self):
        self.assert_call(InsightsReportResult, id=AN_ID, name="n", status="success", clusters=[], report=None)
        self.assert_fields(InsightsReportResult, "clusters", "report", "runs")
        self.assert_fields(InsightsCluster, "id", "parent_id", "level", "name", "num_runs", "stats")
        self.assert_fields(InsightsSummaryReport, "key_points", "highlighted_traces")
        self.assert_fields(InsightsHighlightedTrace, "run_id", "rank", "highlight_reason")

    def test_engine_issue(self):
        self.assert_call(Issue.model_validate, {"id": AN_ID})
        self.assert_fields(Issue, "id", "name", "description", "severity", "status", "tags", "proposed_fix",
                           "fixes", "watching_since", "recurrences_since_watching")
        # `type` is in the REST schema but not a declared field of this type; the value must survive
        issue = Issue.model_validate({"id": AN_ID, "name": "n", "severity": 3, "status": "watching",
                                      "type": "finding"})
        self.assertEqual(issue.type, "finding")


class LangChainNamesTest(SurfaceTestCase):
    """LangChain names of Section 4. Signatures only: no model and no agent is constructed."""

    def test_pii_middleware(self):
        self.assert_call(PIIMiddleware, "email", strategy="redact", apply_to_input=True, apply_to_output=True)

    def test_init_chat_model_takes_a_provider_colon_model_string(self):
        self.assert_call(init_chat_model, "openai:gpt-5.4")

    def test_create_agent(self):
        self.assert_call(create_agent, object(), tools=[], middleware=[])

    def test_gateway_replay_parts(self):
        # The call `gateway_replay()` in utils/offline_capture.py makes. The mock transport reaches the
        # model only through `http_client` and `http_async_client`: if a release renamed either, the
        # replay would stop using the saved responses and try the network instead.
        self.assert_call(httpx.MockTransport, lambda request: None)
        transport = httpx.MockTransport(lambda request: None)
        for http_class in (httpx.Client, httpx.AsyncClient):
            self.assert_call(http_class, transport=transport, trust_env=False)
        # assert_call compares names, so a placeholder stands in for each HTTP client and none is built
        self.assert_call(ChatOpenAI, model="gpt-5.4", api_key="k", base_url="http://offline.invalid/openai/v1",
                         max_retries=0, http_socket_options=(), http_client=object(), http_async_client=object())


if __name__ == "__main__":
    unittest.main()
