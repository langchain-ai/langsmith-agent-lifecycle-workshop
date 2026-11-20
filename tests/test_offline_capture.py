"""utils/offline_capture.py: the capture client, the masking lab, the Gateway replay and the two fixtures.

Nothing is sent. The whole module runs inside `refuse_non_local_connects()`, and every test
fails in `tearDown` if any code tried to reach a non-local address or look up a host name.
The tests that need a particular environment variable start a new Python process (the SDK
reads each variable once and keeps the value); each of those processes holds the same guard
until it ends and reports what the guard refused.

Run: uv run python -m unittest tests.test_offline_capture
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import sys
import unittest
import warnings
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import openai
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langsmith import Client, tracing_context
from langsmith.anonymizer import create_anonymizer

import utils.offline_capture as offline_capture
from utils.offline_capture import (
    DATA,
    GATEWAY_REPLAY_BASE_URL,
    HIDE_INPUTS_PROBE_QUESTION,
    OFFLINE_API_URL,
    OFFLINE_KEY,
    Capture,
    alert_webhook_payload,
    blocked_responses,
    count_payloads_containing,
    gateway_replay,
    hide_inputs_in_subprocess,
    offline_client,
    refuse_non_local_connects,
    scripted_model,
    uploaded_payloads,
)

EMAIL = "jordan.lee@example.com"  # the synthetic address planted in the Module 7 seed
CONTROL = "order ORD-2025-0050"  # no PII: masking must leave it alone
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
QUESTION = f"My email is {EMAIL}. Where is {CONTROL}?"
REPLY = f"I will email {EMAIL} about {CONTROL}."

# Quoted from the three policy pages of docs.langchain.com (the `_source_url` of each entry).
DOCUMENTED_BLOCKS = {
    "spend": (402, '{"type":"error","error":{"message":"request blocked by gateway policies: <POLICY_NAME>"}}'),
    "rate": (429, '{"type":"error","error":{"message":"request blocked by gateway policies: <POLICY_NAME>"}}'),
    "model_access": (
        403,
        '{"error":{"code":null,"message":"request blocked by gateway policies: <POLICY_NAME>",'
        '"param":null,"type":"permission_error"}}',
    ),
}
BLOCKED_PREFIX = "request blocked by gateway policies: "

# The 12 keys listed under "Request Body Template" on https://docs.langchain.com/langsmith/alerts
DOCUMENTED_ALERT_KEYS = [
    "project_name",
    "workspace_name",
    "alert_rule_id",
    "alert_rule_name",
    "alert_rule_description",
    "alert_rule_type",
    "alert_rule_attribute",
    "alert_rule_url",
    "runs_url",
    "triggered_metric_value",
    "triggered_threshold",
    "timestamp",
]

NON_LOCAL_ATTEMPTS: list = []


def setUpModule():
    global NON_LOCAL_ATTEMPTS
    stack = ExitStack()
    NON_LOCAL_ATTEMPTS = stack.enter_context(refuse_non_local_connects())
    # Tracing is off unless a test turns it on for an offline client, whatever the shell exports.
    stack.enter_context(tracing_context(enabled=False))
    unittest.addModuleCleanup(stack.close)


class OfflineTestCase(unittest.TestCase):
    def tearDown(self):
        # Emptied after reading, so that one test's attempt does not also fail every later test.
        attempts, NON_LOCAL_ATTEMPTS[:] = list(NON_LOCAL_ATTEMPTS), []
        self.assertEqual(attempts, [], "this test tried to leave the machine")


def run_agent(middleware, **client_kwargs):
    """One turn of a model-free agent, traced into an offline client. Returns (message texts, capture)."""
    agent = create_agent(scripted_model([REPLY]), tools=[], middleware=middleware)
    client, capture = offline_client(**client_kwargs)
    with tracing_context(enabled=True, client=client):
        state = agent.invoke({"messages": [{"role": "user", "content": QUESTION}]})
    client.flush()
    return [message.content for message in state["messages"]], capture


def pii_middleware():
    return [PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True)]


def email_anonymizer():
    return create_anonymizer([{"pattern": EMAIL_PATTERN, "replace": "<email>"}])


def lab_counts(capture) -> dict:
    """The numbers of the masking lab for one capture, in a form two processes can compare."""
    payloads = uploaded_payloads(capture)
    return {
        "payloads": len(payloads),
        "with_email": count_payloads_containing(capture, EMAIL),
        "with_metadata": sum(bool((payload.get("extra") or {}).get("metadata")) for payload in payloads),
    }


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent

# The guard is entered before anything else is imported and is never left, so nothing can
# leave the child even from a background thread. `os._exit` skips every exit hook.
_CHILD_TEMPLATE = """
import json, os, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]  # the repo root (for utils) and tests/ (for this module)
from utils.offline_capture import refuse_non_local_connects
attempts = refuse_non_local_connects().__enter__()
result = {}
%s
print(json.dumps({"result": result, "non_local_connects": [str(attempt) for attempt in attempts]}))
sys.stdout.flush()
os._exit(0)
"""


def run_child(body: str, **env: str) -> dict:
    """Run `body` in a new Python process whose environment is `PATH`, `HOME` and `env`.

    `body` fills the dictionary `result`. Returns `{"result": ..., "non_local_connects": [...]}`.
    """
    child_env = {name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ}
    child_env.update(env)
    done = subprocess.run(
        [sys.executable, "-c", _CHILD_TEMPLATE % body, str(REPO_ROOT), str(TESTS_DIR)],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if done.returncode != 0:
        raise AssertionError(f"child process failed with {env}:\n{done.stderr.strip()}")
    return json.loads(done.stdout.strip().splitlines()[-1])


class MaskingLabTest(OfflineTestCase):
    """The three runs of Module 7 Section 4: what each control keeps out of the upload."""

    def test_middleware_only_still_uploads_the_email(self):
        texts, capture = run_agent(pii_middleware())
        self.assertEqual(len(texts), 2)
        for text in texts:  # the conversation state is redacted
            self.assertNotIn(EMAIL, text)
            self.assertIn("[REDACTED_EMAIL]", text)
        payloads = uploaded_payloads(capture)
        self.assertGreater(len(payloads), 0)
        self.assertGreater(count_payloads_containing(capture, EMAIL), 0)
        root_inputs = [p["inputs"] for p in payloads if not p.get("parent_run_id") and p.get("inputs")]
        self.assertTrue(root_inputs and all(EMAIL in json.dumps(inputs) for inputs in root_inputs))

    def test_middleware_plus_anonymizer_uploads_no_email_and_keeps_the_control_string(self):
        _, unmasked = run_agent(pii_middleware())
        texts, capture = run_agent(pii_middleware(), anonymizer=email_anonymizer())
        self.assertEqual(count_payloads_containing(capture, EMAIL), 0)
        self.assertEqual(len(uploaded_payloads(capture)), len(uploaded_payloads(unmasked)))
        # The control string is uploaded exactly as often as without the anonymizer.
        self.assertGreater(count_payloads_containing(capture, CONTROL), 0)
        self.assertEqual(count_payloads_containing(capture, CONTROL), count_payloads_containing(unmasked, CONTROL))
        # Every payload that held the address now holds the replacement.
        self.assertEqual(count_payloads_containing(capture, "<email>"), count_payloads_containing(unmasked, EMAIL))
        self.assertTrue(all("[REDACTED_EMAIL]" in text for text in texts))

    def test_anonymizer_only_uploads_no_email_but_the_conversation_keeps_it(self):
        texts, capture = run_agent([], anonymizer=email_anonymizer())
        self.assertGreater(len(uploaded_payloads(capture)), 0)
        self.assertEqual(count_payloads_containing(capture, EMAIL), 0)
        self.assertGreater(count_payloads_containing(capture, CONTROL), 0)
        self.assertEqual(texts, [QUESTION, REPLY])  # no middleware: the model saw the address


_LAB_CHILD = """
import test_offline_capture as lab
from utils.offline_capture import offline_client
texts, capture = lab.run_agent(lab.pii_middleware())
result = lab.lab_counts(capture)
client, _ = offline_client()
result["otel_exporter"] = type(client.otel_exporter).__name__
result["tracing_mode"] = client.tracing_mode
"""


class EnvironmentIndependenceTest(OfflineTestCase):
    """`offline_client()` records the same thing whatever the shell or `.env` sets.

    Section 4 teaches `LANGSMITH_HIDE_INPUTS`, so a learner may well have it set when the
    masking lab runs. Without the fixed defaults the lab's "N of M" would then read 2 of 10 or
    0 of 10 for the middleware-only run, and 0 of 0 with a sampling rate of 0.
    """

    def test_tracing_variables_in_the_environment_do_not_change_the_masking_lab(self):
        _, capture = run_agent(pii_middleware())
        expected = lab_counts(capture)
        self.assertGreater(expected["with_email"], 0)
        self.assertGreater(expected["with_metadata"], 0)
        expected.update(otel_exporter="NoneType", tracing_mode="langsmith")
        for env in (
            {},
            {"LANGSMITH_HIDE_INPUTS": "true", "LANGSMITH_HIDE_OUTPUTS": "true", "LANGSMITH_HIDE_METADATA": "true"},
            {"LANGCHAIN_HIDE_INPUTS": "true", "LANGCHAIN_HIDE_OUTPUTS": "true"},  # the older spelling, still read
            {"LANGSMITH_TRACING_SAMPLING_RATE": "0"},
            {"LANGSMITH_TRACING_MODE": "otel"},
            {"LANGSMITH_OTEL_ENABLED": "true", "LANGSMITH_OTEL_ONLY": "true"},  # the older switches, still read
        ):
            with self.subTest(env=env):
                child = run_child(_LAB_CHILD, **env)
                self.assertEqual(child["non_local_connects"], [])
                self.assertEqual(child["result"], expected)

    def test_an_explicit_argument_still_decides(self):
        _, capture = run_agent(pii_middleware(), hide_inputs=True, hide_outputs=True)
        self.assertGreater(len(uploaded_payloads(capture)), 0)
        self.assertEqual(count_payloads_containing(capture, EMAIL), 0)
        _, capture = run_agent(pii_middleware(), hide_metadata=True)
        self.assertEqual(lab_counts(capture)["with_metadata"], 0)
        _, capture = run_agent(pii_middleware(), tracing_sampling_rate=0.0)
        self.assertEqual(capture.calls, [])


class FixedSettingsTest(OfflineTestCase):
    """The two `Client` settings that would take uploads past the recorder cannot be changed."""

    def test_an_opentelemetry_tracing_mode_is_refused(self):
        # The SDK's OpenTelemetry exporter is not attached to the recorder: it would send the
        # trace to the address and API key in the environment. `None` lets a variable decide.
        for kwargs in (
            {"tracing_mode": "otel"},
            {"tracing_mode": "hybrid"},
            {"tracing_mode": "OTEL"},
            {"tracing_mode": None},
            {"tracing_mode": "otel", "auto_batch_tracing": True},
            {"otel_enabled": True},
            {"otel_enabled": False},
            {"otel_tracer_provider": object()},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "^offline_client: .* is not supported"):
                offline_client(**kwargs)

    def test_automatic_batching_is_refused(self):
        with self.assertRaisesRegex(ValueError, "^offline_client: auto_batch_tracing=True is not supported"):
            offline_client(auto_batch_tracing=True)

    def test_the_fixed_values_can_be_passed_explicitly(self):
        client, capture = offline_client(tracing_mode="langsmith", auto_batch_tracing=False)
        self.assertEqual(client.tracing_mode, "langsmith")
        self.assertIsNone(client.otel_exporter)
        with tracing_context(enabled=True, client=client):
            RunnableLambda(lambda inputs: inputs, name="probe").invoke({"question": QUESTION})
        client.flush()
        self.assertEqual([method for method, _, _ in capture.calls], ["POST", "PATCH"])
        self.assertEqual(count_payloads_containing(capture, EMAIL), 2)


AGENT_ID = "00000000-0000-0000-0000-0000000000a1"
PROJECT_ID = "00000000-0000-0000-0000-0000000000b2"


def agent_reply(method, url, body):
    return 200, {"id": AGENT_ID, "name": "techhub-support", "tracer_session_name": "techhub-production", "items": []}


class CaptureTest(OfflineTestCase):
    def test_runs_are_recorded_as_post_then_patch_on_the_offline_url(self):
        _, capture = run_agent([])
        self.assertTrue(all(url.startswith(OFFLINE_API_URL + "/runs") for _, url, _ in capture.calls))
        methods = [method for method, _, _ in capture.calls]
        self.assertEqual(methods[0], "POST")
        self.assertEqual(methods[-1], "PATCH")
        self.assertEqual(methods.count("POST"), methods.count("PATCH"))
        self.assertEqual(len(uploaded_payloads(capture)), len(capture.calls))

    def test_default_reply_is_200_and_a_responder_can_play_the_server(self):
        client, capture = offline_client()
        reply = client.session.get(f"{OFFLINE_API_URL}/anything")
        self.assertEqual((reply.status_code, reply.json()), (200, {}))

        def responder(method, url, body):
            return (404, {"detail": "no such project"}) if url.endswith("/sessions/missing") else None

        client, capture = offline_client(responder=responder)
        self.assertEqual(client.session.get(f"{OFFLINE_API_URL}/sessions/missing").status_code, 404)
        self.assertEqual(client.session.post(f"{OFFLINE_API_URL}/feedback", data='{"key": "k"}').status_code, 200)
        self.assertEqual(
            capture.calls,
            [("GET", f"{OFFLINE_API_URL}/sessions/missing", None), ("POST", f"{OFFLINE_API_URL}/feedback", '{"key": "k"}')],
        )

    def test_the_newer_sdk_resources_are_captured_too(self):
        # client.runs, client.agents and friends use a second HTTP client inside the SDK. If a
        # package update changes how it is built, offline_client() warns and this test fails.
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            client, capture = offline_client(responder=lambda method, url, body: (200, {"items": []}))

        async def query():
            return [run async for run in client.runs.query(project_ids=["0" * 8 + "-0000-0000-0000-" + "0" * 12], is_root=True)]

        self.assertEqual(asyncio.run(query()), [])
        method, url, body = capture.calls[-1]
        self.assertEqual((method, url), ("POST", f"{OFFLINE_API_URL}/api/v2/runs/query"))
        self.assertTrue(json.loads(body)["is_root"])
        self.assertEqual(uploaded_payloads(capture), [])  # a query is not an upload

    def test_the_sync_generated_resources_are_captured_too(self):
        # client.agents is synchronous and uses a third HTTP client inside the SDK, separate
        # from the one behind the async client.runs. Both must be replaced.
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            client, capture = offline_client(responder=agent_reply)
        agent = client.agents.retrieve(AGENT_ID)
        self.assertEqual(agent.tracer_session_name, "techhub-production")
        self.assertEqual(capture.calls, [("GET", f"{OFFLINE_API_URL}/api/v1/agents/{AGENT_ID}", None)])

    def test_https_requests_to_any_host_are_recorded_and_not_sent(self):
        client, capture = offline_client()
        reply = client.session.get("https://any.host.invalid/x")
        self.assertEqual((reply.status_code, reply.json()), (200, {}))
        self.assertEqual(capture.calls, [("GET", "https://any.host.invalid/x", None)])

    def test_api_url_and_api_key_can_be_passed(self):
        client, _ = offline_client()
        self.assertEqual((client.api_url, client.api_key), (OFFLINE_API_URL, OFFLINE_KEY))
        client, _ = offline_client(api_key="another-placeholder")
        self.assertEqual((client.api_url, client.api_key), (OFFLINE_API_URL, "another-placeholder"))

        async def query(client):
            return [run async for run in client.runs.query(project_ids=[PROJECT_ID], is_root=True)]

        # (api_url, the address the /api/... paths are built on). Nothing is sent to any of
        # them: tearDown fails if a single connection or name lookup was attempted.
        for api_url, base in (
            ("https://api.smith.langchain.com", "https://api.smith.langchain.com"),
            ("https://eu.api.smith.langchain.com", "https://eu.api.smith.langchain.com"),
            ("https://langsmith.example.com/api/v1", "https://langsmith.example.com"),
        ):
            with self.subTest(api_url=api_url), warnings.catch_warnings():
                warnings.simplefilter("error", RuntimeWarning)
                client, capture = offline_client(api_url=api_url, responder=agent_reply)
                self.assertEqual(client.api_url, api_url)
                with tracing_context(enabled=True, client=client):
                    RunnableLambda(lambda inputs: inputs, name="probe").invoke({"question": CONTROL})
                client.flush()
                run_calls = [(method, url) for method, url, _ in capture.calls]
                self.assertEqual(run_calls[0], ("POST", f"{api_url}/runs"))
                self.assertEqual(len(uploaded_payloads(capture)), 2)
                self.assertEqual(count_payloads_containing(capture, CONTROL), 2)
                del capture.calls[:]
                client.request_with_retries("GET", "/api/v2/runs/rules")  # the classic client
                client.agents.retrieve(AGENT_ID)  # the sync generated client
                asyncio.run(query(client))  # the async generated client
                self.assertEqual(
                    [(method, url) for method, url, _ in capture.calls],
                    [
                        ("GET", f"{base}/api/v2/runs/rules"),
                        ("GET", f"{base}/api/v1/agents/{AGENT_ID}"),
                        ("POST", f"{base}/api/v2/runs/query"),
                    ],
                )

    def test_if_the_newer_resources_cannot_be_captured_the_offline_address_only_warns(self):
        broken = mock.patch.object(offline_capture, "_capture_generated_clients", side_effect=AttributeError("renamed"))
        with broken, self.assertWarnsRegex(RuntimeWarning, "AttributeError: renamed.*still captured"):
            client, capture = offline_client()
        with tracing_context(enabled=True, client=client):
            RunnableLambda(lambda inputs: inputs, name="probe").invoke({"question": CONTROL})
        client.flush()
        self.assertEqual(len(uploaded_payloads(capture)), 2)

    def test_if_the_newer_resources_cannot_be_captured_a_real_address_is_refused(self):
        # client.runs and client.agents would otherwise send real requests to that address.
        broken = mock.patch.object(offline_capture, "_capture_generated_clients", side_effect=AttributeError("renamed"))
        with broken, self.assertRaisesRegex(RuntimeError, "https://eu.api.smith.langchain.com.*no client is returned"):
            offline_client(api_url="https://eu.api.smith.langchain.com")

    def test_uploaded_payloads_reads_single_and_batch_requests(self):
        capture = Capture()
        run_id = "01a1f628-153c-7771-b90f-26a8cb94054c"
        capture.calls = [
            ("POST", f"{OFFLINE_API_URL}/runs", json.dumps({"id": run_id, "inputs": {"q": ["nested", {"k": "needle"}]}})),
            ("PATCH", f"{OFFLINE_API_URL}/runs/{run_id}", json.dumps({"outputs": {"a": "hay"}})),
            ("POST", f"{OFFLINE_API_URL}/runs/batch", json.dumps({"post": [{"id": "a"}], "patch": [{"error": "needle"}]})),
            ("POST", f"{OFFLINE_API_URL}/api/v2/runs/query", json.dumps({"filter": "needle"})),
            ("POST", f"{OFFLINE_API_URL}/feedback", json.dumps({"comment": "needle"})),
            ("GET", f"{OFFLINE_API_URL}/runs/{run_id}", None),
        ]
        self.assertEqual(len(uploaded_payloads(capture)), 4)
        self.assertEqual(count_payloads_containing(capture, "needle"), 2)
        self.assertEqual(count_payloads_containing(capture, "absent"), 0)

    def test_a_run_upload_that_cannot_be_read_is_an_error_and_not_a_count_of_zero(self):
        part = 'Content-Disposition: form-data; name="post.1.inputs"'
        multipart = f'--boundary\r\n{part}\r\n\r\n{{"q": "{EMAIL}"}}\r\n--boundary--'
        for url, body in (
            (f"{OFFLINE_API_URL}/runs/multipart", multipart),
            (f"{OFFLINE_API_URL}/runs", "not json"),
            (f"{OFFLINE_API_URL}/runs/batch", json.dumps([{"inputs": EMAIL}])),  # JSON, but not an object
        ):
            with self.subTest(url=url):
                capture = Capture()
                capture.calls = [("POST", url, body)]
                with self.assertRaisesRegex(ValueError, f"cannot read the run upload POST {re.escape(url)}"):
                    uploaded_payloads(capture)
                with self.assertRaisesRegex(ValueError, "cannot read the run upload"):
                    count_payloads_containing(capture, EMAIL)

    def test_what_a_batching_client_really_uploads_is_an_error_and_not_a_count_of_zero(self):
        # A `Client` with automatic batching, built by hand because offline_client() refuses to
        # build one. It uploads the run as multipart form data, which holds the address but is
        # not JSON. If a package update changes that route, this test fails.
        sdk_log = logging.getLogger("langsmith.client")
        self.addCleanup(sdk_log.setLevel, sdk_log.level)
        sdk_log.setLevel(logging.ERROR)  # the upload thread warns that the answering server offers no compression
        capture = Capture()
        client = Client(**{**offline_capture._offline_client_defaults(), "auto_batch_tracing": True})
        client.session.mount("http://", capture)
        client.session.mount("https://", capture)
        with tracing_context(enabled=True, client=client):
            RunnableLambda(lambda inputs: inputs, name="probe").invoke({"question": QUESTION})
        client.flush()
        sent = [(method, url) for method, url, _ in capture.calls]
        self.assertEqual(sent, [("POST", f"{OFFLINE_API_URL}/runs/multipart")])
        self.assertIn(EMAIL, capture.calls[0][2])
        with self.assertRaisesRegex(ValueError, "cannot read the run upload POST .*/runs/multipart"):
            count_payloads_containing(capture, EMAIL)

    def test_a_string_that_is_only_a_dictionary_key_is_found(self):
        capture = Capture()
        capture.calls = [("POST", f"{OFFLINE_API_URL}/runs", json.dumps({"inputs": {"by_email": {EMAIL: ["ORD-1"]}}}))]
        self.assertEqual(count_payloads_containing(capture, EMAIL), 1)
        self.assertEqual(count_payloads_containing(capture, "ORD-2"), 0)


class ScriptedModelTest(OfflineTestCase):
    def test_replies_come_back_in_order_then_the_model_refuses(self):
        model = scripted_model(["first", AIMessage(content="second")])
        self.assertEqual(model.invoke("a").content, "first")
        self.assertEqual(model.invoke("b").content, "second")
        with self.assertRaisesRegex(RuntimeError, "no replies left"):
            model.invoke("c")

    def test_the_script_survives_copies_and_tool_binding(self):
        # What an agent harness does to the model it is given (the reason the replies are module-level).
        model = scripted_model(["one", "two", "three"])
        self.assertEqual(model.model_copy(deep=True).invoke("a").content, "one")
        self.assertEqual(model.bind_tools([]).invoke("b").content, "two")
        self.assertEqual(model.invoke("c").content, "three")

    def test_two_models_do_not_share_a_script(self):
        main, specialist = scripted_model(["main"]), scripted_model(["specialist"])
        self.assertEqual(specialist.invoke("a").content, "specialist")
        self.assertEqual(main.invoke("a").content, "main")


_AMBIENT_TRACING_CHILD = """
import langsmith
from utils.offline_capture import gateway_replay, offline_client, scripted_model
client, capture = offline_client()
langsmith.configure(client=client)

def recorded(call):
    before = len(capture.calls)
    try:
        outcome = call().content
    except Exception as exc:
        outcome = type(exc).__name__
    client.flush()
    return [outcome, len(capture.calls) - before]

result["scripted_before"] = recorded(lambda: scripted_model(["hi"]).invoke("ping"))
result["replay"] = {kind: recorded(lambda: gateway_replay(kind).invoke("ping")) for kind in ("spend", "rate", "model_access")}
result["scripted_after"] = recorded(lambda: scripted_model(["hi"]).invoke("ping"))
"""


class GatewayReplayTest(OfflineTestCase):
    def blocked(self, kind):
        with self.assertRaises(openai.APIStatusError) as caught:
            gateway_replay(kind).invoke("ping")
        return caught.exception

    def test_fixture_is_the_documented_shape_with_its_source(self):
        saved = blocked_responses()
        self.assertEqual(list(saved), ["spend", "rate", "model_access"])
        for kind, (status, documented_body) in DOCUMENTED_BLOCKS.items():
            with self.subTest(kind=kind):
                entry = saved[kind]
                self.assertEqual(entry["status"], status)
                self.assertTrue(entry["_source_url"].startswith("https://docs.langchain.com/"))
                self.assertIn("not captured output", entry["_note"])
                message = entry["body"]["error"]["message"]
                self.assertTrue(message.startswith(BLOCKED_PREFIX))
                policy_name = message[len(BLOCKED_PREFIX) :]
                self.assertTrue(policy_name)
                body_text = json.dumps(entry["body"], separators=(",", ":"))
                self.assertEqual(body_text.replace(policy_name, "<POLICY_NAME>"), documented_body)
        self.assertEqual([kind for kind, entry in saved.items() if "Retry-After" in entry["headers"]], ["rate"])

    def test_policy_types_and_exceptions_are_the_answer_key_of_s4_blocks(self):
        # An answer built from the fixture and the replayed exceptions must pass check("s4_blocks", ...).
        # The checker compares with answers.json, or with answer_hashes.json where the plain key is removed.
        built = {
            str(entry["status"]): {"policy_type": entry["policy_type"], "exception": type(self.blocked(kind)).__name__}
            for kind, entry in blocked_responses().items()
        }
        self.assertEqual(sorted(built), ["402", "403", "429"])
        answers_file = DATA / "answers.json"
        if answers_file.exists():
            answers = json.loads(answers_file.read_text())["s4_blocks"]
            self.assertEqual(built, {status: answers[status] for status in built})
        hashes = json.loads((DATA / "answer_hashes.json").read_text())["fields"]["s4_blocks"]
        for status, row in built.items():
            with self.subTest(status=status):
                canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), hashes[status])

    def test_rate_limit_raises_rate_limit_error_with_a_readable_retry_after(self):
        exc = self.blocked("rate")
        self.assertIs(type(exc), openai.RateLimitError)
        self.assertEqual(exc.status_code, 429)
        self.assertGreater(int(exc.response.headers["Retry-After"]), 0)
        self.assertEqual(exc.response.headers["Retry-After"], blocked_responses()["rate"]["headers"]["Retry-After"])

    def test_spend_limit_raises_the_generic_status_error_with_402(self):
        exc = self.blocked("spend")
        self.assertIs(type(exc), openai.APIStatusError)  # the OpenAI SDK has no dedicated class for 402
        self.assertEqual(exc.status_code, 402)
        self.assertNotIn("Retry-After", exc.response.headers)

    def test_model_access_raises_permission_denied_error(self):
        exc = self.blocked("model_access")
        self.assertIs(type(exc), openai.PermissionDeniedError)
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.body["type"], "permission_error")

    def test_every_block_names_its_policy(self):
        for kind, entry in blocked_responses().items():
            with self.subTest(kind=kind):
                exc = self.blocked(kind)
                expected = entry["body"]["error"]["message"]
                self.assertIn(BLOCKED_PREFIX, exc.response.text)
                self.assertEqual(exc.body["message"], expected)
                self.assertIn(expected, str(exc))
                self.assertEqual(json.loads(exc.response.text), entry["body"])

    def test_async_calls_are_replayed_too(self):
        with self.assertRaises(openai.RateLimitError):
            asyncio.run(gateway_replay("rate").ainvoke("ping"))

    def test_the_model_points_at_the_offline_url_and_never_retries(self):
        model = gateway_replay("rate")
        self.assertEqual(model.openai_api_base, GATEWAY_REPLAY_BASE_URL)
        self.assertEqual(GATEWAY_REPLAY_BASE_URL, "http://offline.invalid/openai/v1")
        self.assertEqual(model.max_retries, 0)

    def test_unknown_kind_is_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, "spend, rate, model_access"):
            gateway_replay("pii")

    def test_a_direct_call_is_never_traced(self):
        # Without this a learner with LANGSMITH_TRACING=true would upload three failed
        # ChatOpenAI runs, with tracebacks, to their own project every time the cell runs.
        client, capture = offline_client()

        async def astream(model):
            return [chunk async for chunk in model.astream("ping")]

        calls = {
            "invoke": lambda model: model.invoke("ping"),
            "ainvoke": lambda model: asyncio.run(model.ainvoke("ping")),
            "batch": lambda model: model.batch(["ping", "ping"]),
            "abatch": lambda model: asyncio.run(model.abatch(["ping", "ping"])),
            "stream": lambda model: list(model.stream("ping")),
            "astream": lambda model: asyncio.run(astream(model)),
        }
        with tracing_context(enabled=True, client=client):
            scripted_model(["hi"]).invoke("ping")  # the control: an ordinary model call is traced here
            client.flush()
            control = len(capture.calls)
            self.assertGreater(control, 0)
            for kind in blocked_responses():
                for name, call in calls.items():
                    with self.subTest(kind=kind, call=name):
                        with self.assertRaises(openai.APIStatusError):
                            call(gateway_replay(kind))
                        client.flush()
                        self.assertEqual(len(capture.calls), control)
            scripted_model(["hi"]).invoke("ping")  # and tracing is still on afterwards
            client.flush()
            self.assertEqual(len(capture.calls), 2 * control)

    def test_with_tracing_switched_on_in_the_environment_the_replay_uploads_nothing(self):
        # LANGSMITH_TRACING=true as a keyed learner has it. langsmith.configure() makes the
        # recorder the client that such tracing uploads to, so the result can be counted.
        child = run_child(
            _AMBIENT_TRACING_CHILD,
            LANGSMITH_TRACING="true",
            LANGSMITH_API_KEY=OFFLINE_KEY,
            LANGSMITH_ENDPOINT=OFFLINE_API_URL,
        )
        self.assertEqual(child["non_local_connects"], [])
        result = child["result"]
        self.assertEqual(result["scripted_before"][0], "hi")
        self.assertGreater(result["scripted_before"][1], 0)  # the control: tracing really is on
        self.assertEqual(
            result["replay"],
            {"spend": ["APIStatusError", 0], "rate": ["RateLimitError", 0], "model_access": ["PermissionDeniedError", 0]},
        )
        self.assertEqual(result["scripted_after"], result["scripted_before"])

    def test_inside_a_traced_chain_only_the_model_run_is_left_out(self):
        client, capture = offline_client()
        chain = RunnableLambda(lambda text: gateway_replay("rate").invoke(text), name="outer")
        with tracing_context(enabled=True, client=client):
            with self.assertRaises(openai.RateLimitError):
                chain.invoke("ping")
        client.flush()
        started = [json.loads(body)["name"] for method, _, body in capture.calls if method == "POST"]
        self.assertEqual(started, ["outer"])
        self.assertEqual(count_payloads_containing(capture, BLOCKED_PREFIX), 1)  # the chain's own error text


class AlertWebhookPayloadTest(OfflineTestCase):
    def test_payload_has_exactly_the_12_documented_keys(self):
        self.assertEqual(len(DOCUMENTED_ALERT_KEYS), 12)
        self.assertEqual(list(alert_webhook_payload()), DOCUMENTED_ALERT_KEYS)

    def test_file_carries_its_source_and_a_note(self):
        data = json.loads((DATA / "alert_webhook_payload.json").read_text())
        self.assertTrue(data["_source_url"].startswith("https://docs.langchain.com/"))
        self.assertIn("not captured output", data["_note"])
        self.assertIn("UNVERIFIED", data["_note"])
        self.assertEqual(list(data["_field_descriptions"]), DOCUMENTED_ALERT_KEYS)
        self.assertEqual([key for key in data if not key.startswith("_")], DOCUMENTED_ALERT_KEYS)
        self.assertEqual(sorted(key for key in data if key.startswith("_")), ["_field_descriptions", "_note", "_source_url"])


class HideInputsSpellingTest(OfflineTestCase):
    def test_only_lowercase_true_hides_the_inputs(self):
        for value, hidden in (("true", True), ("True", False), ("1", False)):
            with self.subTest(LANGSMITH_HIDE_INPUTS=value):
                result = hide_inputs_in_subprocess(value)
                expected = {} if hidden else {"question": HIDE_INPUTS_PROBE_QUESTION}
                self.assertEqual(result["uploaded_inputs"], expected)
                self.assertEqual(result["non_local_connects"], [])


class RefuseNonLocalConnectsTest(OfflineTestCase):
    def test_non_local_attempts_are_refused_and_listed_and_local_ones_pass(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)  # two local connections are made below
        with refuse_non_local_connects() as attempts:
            local = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.addCleanup(local.close)
            local.connect(listener.getsockname())  # loopback passes
            remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.addCleanup(remote.close)
            with self.assertRaises(ConnectionRefusedError):
                remote.connect(("192.0.2.1", 443))  # a documentation-only address (RFC 5737)
            with self.assertRaises(socket.gaierror):
                socket.getaddrinfo("offline.invalid", 80)
            # connect_ex is the variant that returns an error number; asyncio uses it.
            other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.addCleanup(other.close)
            with self.assertRaises(ConnectionRefusedError):
                other.connect_ex(("192.0.2.1", 80))
            also_local = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.addCleanup(also_local.close)
            self.assertEqual(also_local.connect_ex(listener.getsockname()), 0)  # loopback passes
            self.assertEqual(attempts, [("192.0.2.1", 443), ("name lookup", "offline.invalid"), ("192.0.2.1", 80)])
        self.assertEqual(NON_LOCAL_ATTEMPTS, [])  # the inner guard caught them before the module's guard


if __name__ == "__main__":
    unittest.main()
