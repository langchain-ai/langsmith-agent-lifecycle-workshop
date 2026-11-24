"""The LangSmith link helpers work without a usable key, and the old call forms keep working.

Four credential states are covered: no key, the `.env.example` placeholder, a key
that LangSmith rejects, and a key that it accepts. Nothing leaves the machine:
every HTTP request is recorded and answered locally, every socket connect is
recorded and refused, and the agent runs on a fake model.

Run: uv run python -m unittest tests.test_langsmith_links_keyless
"""

import contextlib
import io
import json
import os
import re
import socket
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import langsmith as ls
import requests
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langsmith import utils as ls_utils
from requests.adapters import HTTPAdapter

from utils import langsmith_links
from utils.langsmith_links import (
    DEFAULT_PROJECT,
    collect_run_tree,
    langsmith_status,
    print_run_tree,
    project_url,
    setup_langsmith,
    trace_link,
    trace_url,
)

# A reserved top-level domain that never resolves: even a request that slipped
# past the guard below could not reach a real service.
ENDPOINT = "https://langsmith.invalid"
FAKE_KEY = "not-a-real-key"
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "22222222-2222-4222-8222-222222222222"
PROJECT = {
    "id": PROJECT_ID,
    "tenant_id": TENANT_ID,
    "name": DEFAULT_PROJECT,
    "start_time": "2026-01-01T00:00:00+00:00",
    "reference_dataset_id": None,
}
# The client cannot derive a web address from the stand-in endpoint, so it uses its default one.
PROJECT_URL = f"https://smith.langchain.com/o/{TENANT_ID}/projects/p/{PROJECT_ID}"
UNAVAILABLE = "⏭️  LangSmith unavailable: "
LABS_STILL_RUN = ". The labs still run; traces print here instead of linking to LangSmith.\n"

REQUESTS = []  # (method, url) of every HTTP request the code under test tried to send
SOCKETS = []  # every address any code tried to connect to
_reply = {"fn": None}
_patches = []


def rejected(request):
    return 401, b'{"detail":"Invalid token"}'


def forbidden(request):
    return 403, b'{"error":"Forbidden"}'


def accepted(request):
    return 200, json.dumps([PROJECT]).encode()


def _send(self, request, **kwargs):
    REQUESTS.append((request.method, request.url))
    status, body = _reply["fn"](request)
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.request = request
    response.url = request.url
    response.headers["content-type"] = "application/json"
    response.reason = {200: "OK", 401: "Unauthorized", 403: "Forbidden"}.get(status, "")
    return response


def _connect(self, address):
    SOCKETS.append(address)
    raise ConnectionRefusedError(f"test guard: blocked connect to {address}")


def setUpModule():
    _patches.append(mock.patch.object(HTTPAdapter, "send", _send))
    _patches.append(mock.patch.object(socket.socket, "connect", _connect))
    for patch in _patches:
        patch.start()


def tearDownModule():
    while _patches:
        _patches.pop().stop()


class FakeToolModel(BaseChatModel):
    """Calls `get_order_status` once, then answers. No network, no key."""

    @property
    def _llm_type(self) -> str:
        return "fake-tool-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if messages[-1].type == "tool":
            message = AIMessage(content="Order ORD-2025-0050 has shipped.")
        else:
            call = {"name": "get_order_status", "args": {"order_id": "ORD-2025-0050"}, "id": "call_1"}
            message = AIMessage(content="", tool_calls=[call])
        return ChatResult(generations=[ChatGeneration(message=message)])


@tool
def get_order_status(order_id: str) -> str:
    """Look up the status of one order."""
    return f"Order {order_id}: Shipped"


def run_agent():
    agent = create_agent(FakeToolModel(), tools=[get_order_status], name="deep_support_agent")
    return agent.invoke({"messages": [{"role": "user", "content": "Where is ORD-2025-0050?"}]})


def tree(run):
    """(name, run type, children) for a collected run, children in start order."""
    children = sorted(run.child_runs, key=lambda child: child.start_time)
    return (run.name, run.run_type, [tree(child) for child in children])


AGENT_TREE = (
    "deep_support_agent",
    "chain",
    [
        ("model", "chain", [("FakeToolModel", "llm", [])]),
        ("tools", "chain", [("get_order_status", "tool", [])]),
        ("model", "chain", [("FakeToolModel", "llm", [])]),
    ],
)


class LinksTestCase(unittest.TestCase):
    """Each test gets its own environment, a fresh probe result and an empty request log."""

    def use_env(self, reply=rejected, **env):
        """Replace every LangSmith variable with `env`, and answer HTTP requests with `reply`."""
        kept = {k: v for k, v in os.environ.items() if not k.startswith(("LANGSMITH_", "LANGCHAIN_"))}
        # Never read a local LangSmith profile file: point the client at a path that does not exist.
        env.setdefault("LANGSMITH_CONFIG_FILE", os.path.join(os.sep, "nonexistent", "langsmith-config.json"))
        env.setdefault("LANGSMITH_TRACING", "false")
        patch = mock.patch.dict(os.environ, {**kept, **env}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        _reply["fn"] = reply
        self._reset()
        self.addCleanup(self._reset)

    @staticmethod
    def _reset():
        REQUESTS.clear()
        SOCKETS.clear()
        langsmith_status.cache_clear()
        langsmith_links._project_base_url.cache_clear()
        ls_utils.get_env_var.cache_clear()  # the SDK caches the first LANGSMITH_TRACING value it reads
        ls.configure(enabled=None)  # undo setup_langsmith()'s process-wide switch

    def tearDown(self):
        self.assertEqual(SOCKETS, [], "code under test tried to open a socket")

    def printed(self, fn, *args, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = fn(*args, **kwargs)
        return result, out.getvalue()

    def traced(self, label="Order status, verified customer"):
        """Run the fake-model agent inside `with trace_link(label) as cb:`; return (cb, printed text)."""

        def block():
            with trace_link(label) as cb:
                run_agent()
            return cb

        return self.printed(block)


class UnavailableStatesTest(LinksTestCase):
    """States A to C: `LANGSMITH_TRACING=true` as `.env.example` ships it, and no usable key."""

    def assert_local_trace(self, reason, expected_requests):
        with self.assertNoLogs("langsmith", level="WARNING"):
            available, setup_line = self.printed(setup_langsmith)
            self.assertIs(available, False)
            self.assertEqual(setup_line, f"{UNAVAILABLE}{reason}{LABS_STILL_RUN}")
            self.assertEqual(langsmith_status(), (False, reason))
            # Uploads are off although the environment says LANGSMITH_TRACING=true.
            self.assertIs(ls_utils.tracing_is_enabled(), False)

            cb, text = self.traced()
            self.traced("A second block")
        self.assertEqual([tree(run) for run in cb.traced_runs], [AGENT_TREE])
        self.assertTrue(text.startswith("\n🧾 Order status, verified customer (local trace, not uploaded):\n"), text)
        self.assertIn("deep_support_agent  [chain]", text)
        self.assertIn("      └─ get_order_status  [tool]", text)
        self.assertIn("args={'order_id': 'ORD-2025-0050'}", text)
        self.assertNotIn("🔗", text)
        # The answer is cached, including "no": later blocks do not ask again.
        self.assertEqual(len(REQUESTS), expected_requests, REQUESTS)

    def test_no_key_makes_no_request(self):
        self.use_env(LANGSMITH_TRACING="true", LANGSMITH_ENDPOINT=ENDPOINT)
        self.assert_local_trace("LANGSMITH_API_KEY is not set", expected_requests=0)

    def test_empty_key_counts_as_not_set(self):
        self.use_env(LANGSMITH_TRACING="true", LANGSMITH_ENDPOINT=ENDPOINT, LANGSMITH_API_KEY="  ")
        self.assert_local_trace("LANGSMITH_API_KEY is not set", expected_requests=0)

    def test_env_example_placeholder_makes_no_request(self):
        # The three LangSmith lines of .env.example, copied unchanged.
        self.use_env(
            LANGSMITH_TRACING="true",
            LANGSMITH_API_KEY="<langsmith-api-key>",
            LANGSMITH_ENDPOINT="<langsmith-endpoint>",
        )
        self.assert_local_trace("LANGSMITH_API_KEY is still the .env.example placeholder", expected_requests=0)

    def test_rejected_key_makes_exactly_one_request(self):
        self.use_env(rejected, LANGSMITH_TRACING="true", LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.assert_local_trace("LangSmith rejected the request (LangSmithAuthError)", expected_requests=1)
        method, url = REQUESTS[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith(f"{ENDPOINT}/sessions?"), url)

    def test_forbidden_key_makes_exactly_one_request(self):
        self.use_env(forbidden, LANGSMITH_TRACING="true", LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.assert_local_trace("LangSmith rejected the request (LangSmithError)", expected_requests=1)

    def test_legacy_key_variable_is_probed_too(self):
        self.use_env(rejected, LANGSMITH_TRACING="true", LANGCHAIN_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.assert_local_trace("LangSmith rejected the request (LangSmithAuthError)", expected_requests=1)

    def test_network_cut_does_not_raise(self):
        def cut(request):
            raise requests.ConnectionError("network unreachable")

        self.use_env(cut, LANGSMITH_TRACING="true", LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.assert_local_trace("LangSmith rejected the request (LangSmithConnectionError)", expected_requests=1)

    def test_reply_that_is_not_langsmith_does_not_raise(self):
        # For example a proxy login page: status 200, but not the JSON the client expects.
        self.use_env(
            lambda request: (200, b"<html>Sign in to continue</html>"),
            LANGSMITH_TRACING="true",
            LANGSMITH_API_KEY=FAKE_KEY,
            LANGSMITH_ENDPOINT=ENDPOINT,
        )
        self.assert_local_trace("the LangSmith check failed (JSONDecodeError)", expected_requests=1)


class AvailableStateTest(LinksTestCase):
    """State D: LangSmith accepts the key. Tracing stays off here so that the agent run uploads nothing."""

    def setUp(self):
        self.use_env(accepted, LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)

    def test_setup_prints_the_project_link(self):
        available, setup_line = self.printed(setup_langsmith)
        self.assertIs(available, True)
        self.assertEqual(setup_line, f"📊 All traces from this workshop: {PROJECT_URL}\n")
        self.assertEqual(langsmith_status(), (True, ""))

    def test_trace_link_prints_a_link_and_yields_the_run(self):
        self.printed(setup_langsmith)
        cb, text = self.traced()
        self.assertEqual([tree(run) for run in cb.traced_runs], [AGENT_TREE])
        root = cb.traced_runs[0]
        self.assertEqual(text, f"\n🔗 Order status, verified customer: {PROJECT_URL}/r/{root.id}\n")
        # One probe for the Setup line, the status and the link together.
        self.assertEqual(len(REQUESTS), 1, REQUESTS)

    def test_setup_leaves_tracing_as_configured(self):
        self.use_env(accepted, LANGSMITH_TRACING="true", LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.printed(setup_langsmith)
        self.assertIs(ls_utils.tracing_is_enabled(), True)


class RunTreeTest(LinksTestCase):
    """What `with trace_link(...) as cb:` and `collect_run_tree()` hand back, with no key."""

    def setUp(self):
        self.use_env()

    def test_agent_run_is_one_root_with_nested_children(self):
        cb, _ = self.traced()
        self.assertEqual(len(cb.traced_runs), 1)
        root = cb.traced_runs[0]
        self.assertEqual(tree(root), AGENT_TREE)
        self.assertIsNone(root.parent_run_id)
        # The root carries what an evaluator written as `def evaluator(run)` reads.
        self.assertEqual(root.inputs["messages"][0]["content"], "Where is ORD-2025-0050?")
        self.assertIn("messages", root.outputs)
        self.assertEqual(REQUESTS, [])

    def test_collect_run_tree_gives_the_same_tree_and_prints_nothing(self):
        def block():
            with collect_run_tree() as cb:
                run_agent()
            return cb

        cb, text = self.printed(block)
        self.assertEqual([tree(run) for run in cb.traced_runs], [AGENT_TREE])
        self.assertEqual(text, "")

    def test_a_block_does_not_see_runs_from_outside_it(self):
        first, _ = self.traced("first")
        run_agent()  # outside any block
        second, _ = self.traced("second")
        self.assertEqual(len(first.traced_runs), 1)
        self.assertEqual(len(second.traced_runs), 1)
        self.assertNotEqual(first.traced_runs[0].id, second.traced_runs[0].id)

    def test_block_without_a_langchain_run(self):
        def block():
            with trace_link("Nothing traced") as cb:
                pass
            return cb

        cb, text = self.printed(block)
        self.assertEqual(cb.traced_runs, [])
        self.assertEqual(text, "(No LangChain run captured in this block.)\n")

    def test_an_error_inside_the_block_is_not_swallowed(self):
        with self.assertRaises(ZeroDivisionError):
            with trace_link("Failing block"):
                1 / 0

    def test_print_run_tree_format(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def run(name, run_type, begin_ms, end_ms, children=(), inputs=None, error=None):
            return SimpleNamespace(
                name=name,
                run_type=run_type,
                start_time=start + timedelta(milliseconds=begin_ms),
                end_time=None if end_ms is None else start + timedelta(milliseconds=end_ms),
                inputs=inputs or {},
                error=error,
                child_runs=list(children),
            )

        root = run(
            "deep_support_agent",
            "chain",
            0,
            40,
            children=[
                # Listed out of order: children print in start order.
                run("get_order_status", "tool", 20, 25, inputs={"input": "{'order_id': 'ORD-1'}"},
                    error="ValueError('boom')\nTraceback ..."),
                run("model", "chain", 5, 15, children=[run("FakeToolModel", "llm", 6, None)]),
            ],
        )
        _, text = self.printed(print_run_tree, root)
        self.assertEqual(
            text.splitlines(),
            [
                "deep_support_agent  [chain]  40 ms",
                "   └─ model  [chain]  10 ms",
                "      └─ FakeToolModel  [llm]  nan ms",
                "   └─ get_order_status  [tool]  5 ms  args={'order_id': 'ORD-1'}  ERROR: ValueError('boom')",
            ],
        )


class OldCallFormTest(LinksTestCase):
    """Modules 4 and 5 call `project_url()` in Setup and `with trace_link("..."):` without `as`."""

    def test_default_project_name(self):
        self.assertEqual(DEFAULT_PROJECT, "langsmith-agent-lifecycle-workshop")

    def test_project_url_and_trace_url(self):
        self.use_env(accepted, LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.assertEqual(project_url(), PROJECT_URL)
        self.assertEqual(trace_url("abc"), f"{PROJECT_URL}/r/abc")
        self.assertEqual(project_url(), PROJECT_URL)
        self.assertEqual(len(REQUESTS), 1, "the project lookup is cached")
        self.assertIn(f"name={DEFAULT_PROJECT}", REQUESTS[0][1])

    def test_project_name_comes_from_the_argument_or_the_environment(self):
        self.use_env(accepted, LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT, LANGSMITH_PROJECT="from-env")
        project_url()
        project_url("from-argument")
        self.assertEqual(len(REQUESTS), 2)
        self.assertIn("name=from-env", REQUESTS[0][1])
        self.assertIn("name=from-argument", REQUESTS[1][1])

    def test_project_url_creates_a_missing_project(self):
        def fresh_workspace(request):
            if request.method == "GET":
                return 200, b"[]"
            return 200, json.dumps(PROJECT).encode()

        self.use_env(fresh_workspace, LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.assertEqual(project_url(), PROJECT_URL)
        self.assertEqual([method for method, _ in REQUESTS], ["GET", "POST"])
        self.assertEqual(REQUESTS[1][1], f"{ENDPOINT}/sessions")

    def test_project_url_still_raises_when_the_key_is_rejected(self):
        self.use_env(rejected, LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        with self.assertRaises(ls_utils.LangSmithAuthError):
            project_url()

    def test_trace_link_without_as_prints_the_link(self):
        self.use_env(accepted, LANGSMITH_API_KEY=FAKE_KEY, LANGSMITH_ENDPOINT=ENDPOINT)
        self.printed(project_url)  # the Module 4 Setup cell; setup_langsmith() is never called

        def block():
            with trace_link("Scope guard"):
                run_agent()

        _, text = self.printed(block)
        self.assertRegex(text, rf"^\n🔗 Scope guard: {re.escape(PROJECT_URL)}/r/[0-9a-f-]{{36}}\n$")
        self.assertEqual(len(REQUESTS), 1, REQUESTS)

    def test_trace_link_without_as_and_without_a_key_prints_the_tree(self):
        self.use_env()

        def block():
            with trace_link("Scope guard"):
                run_agent()

        _, text = self.printed(block)
        self.assertTrue(text.startswith("\n🧾 Scope guard (local trace, not uploaded):\ndeep_support_agent  [chain]"), text)
        self.assertEqual(REQUESTS, [])


if __name__ == "__main__":
    unittest.main()
