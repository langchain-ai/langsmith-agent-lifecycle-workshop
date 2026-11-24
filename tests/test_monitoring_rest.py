"""utils/monitoring_rest.py: the two run-rule requests of Module 7, checked on what would be sent.

Nothing is sent. Each test builds the capture client of `utils/offline_capture.py`, which records
every request and answers it locally, and the whole module runs inside
`refuse_non_local_connects()`: a test fails in `tearDown` if any code tried to reach a non-local
address or look up a host name. What a real LangSmith server answers to these requests is not
tested here and is UNVERIFIED.

Run: uv run python -m unittest tests.test_monitoring_rest
"""

import ast
import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from langsmith import tracing_context
from langsmith import utils as ls_utils

from evaluators import WRONG_RETURN_WINDOW_SOURCE
from utils import monitoring_rest
from utils.monitoring_local import FILTERS
from utils.monitoring_rest import code_evaluator_rule, create_rule_once, list_rules, ls, queue_rule
from utils.offline_capture import offline_client, refuse_non_local_connects

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
QUEUE_ID = "44444444-4444-4444-8444-444444444444"
RULE_ID = "66666666-6666-4666-8666-666666666666"

# Five shapes of LANGSMITH_ENDPOINT, and the address the documented `/api/...` paths must be built on.
# The last three are self-hosted forms; `.invalid` never resolves.
ENDPOINT_SHAPES = {
    "https://api.smith.langchain.com": "https://api.smith.langchain.com",
    "https://eu.api.smith.langchain.com": "https://eu.api.smith.langchain.com",
    "https://langsmith.invalid/api/v1": "https://langsmith.invalid",
    "https://langsmith.invalid/api": "https://langsmith.invalid",
    "https://langsmith.invalid/prefix/api/v1": "https://langsmith.invalid/prefix",
}

# The request fields of `POST /api/v1/runs/rules` that the research for this module confirmed in the
# REST reference (evaluator attachment and automation). A body may use these names and no others.
DOCUMENTED_RULE_FIELDS = {
    "display_name",
    "session_id",
    "evaluator_id",
    "sampling_rate",
    "filter",
    "backfill_from",
    "code_evaluators",
    "group_by",
    "add_to_annotation_queue_id",
    "add_to_dataset_id",
    "webhooks",
    "extend_only",
}
DOCUMENTED_CODE_EVALUATOR_FIELDS = {"code", "language"}

NON_LOCAL_ATTEMPTS: list = []


def setUpModule():
    global NON_LOCAL_ATTEMPTS
    stack = ExitStack()
    NON_LOCAL_ATTEMPTS = stack.enter_context(refuse_non_local_connects())
    stack.enter_context(tracing_context(enabled=False))
    unittest.addModuleCleanup(stack.close)


def server(existing=(), pages=None, refuse=None):
    """A responder for the capture client: lists `existing` rules, and stores what is posted."""

    def respond(method, url, body):
        path = urlsplit(url).path
        if refuse and method in refuse:
            return refuse[method], {"detail": "refused by the test"}
        if method == "GET" and path.endswith("/api/v2/runs/rules"):
            if pages:
                cursor = parse_qs(urlsplit(url).query).get("cursor", ["0"])[0]
                return 200, pages[cursor]
            return 200, {"items": list(existing), "next_cursor": None}
        if method == "POST" and path.endswith("/api/v1/runs/rules"):
            return 200, {**json.loads(body), "id": RULE_ID}
        return None

    return respond


def bodies(capture, method="POST"):
    return [json.loads(body) for verb, _, body in capture.calls if verb == method and body]


class RestTestCase(unittest.TestCase):
    def tearDown(self):
        attempts, NON_LOCAL_ATTEMPTS[:] = list(NON_LOCAL_ATTEMPTS), []
        self.assertEqual(attempts, [], "this test tried to leave the machine")


class UrlTest(RestTestCase):
    def test_both_requests_reach_the_documented_url_for_five_endpoint_shapes(self):
        body = code_evaluator_rule(project_id=PROJECT_ID, code=WRONG_RETURN_WINDOW_SOURCE)
        for endpoint, origin in ENDPOINT_SHAPES.items():
            with self.subTest(endpoint=endpoint):
                client, capture = offline_client(api_url=endpoint, responder=server())
                rule = create_rule_once(client, body)
                self.assertEqual(rule["id"], RULE_ID)
                (list_method, list_url, _), (create_method, create_url, sent) = capture.calls
                self.assertEqual((list_method, list_url.split("?")[0]), ("GET", f"{origin}/api/v2/runs/rules"))
                self.assertEqual(parse_qs(urlsplit(list_url).query), {"project_id": [PROJECT_ID], "type": ["PROJECT"], "page_size": ["100"]})
                self.assertEqual((create_method, create_url), ("POST", f"{origin}/api/v1/runs/rules"))
                self.assertEqual(json.loads(sent), body)

    def test_a_short_path_is_refused_before_anything_is_sent(self):
        client, capture = offline_client()
        for path in ("/runs/rules", "runs/rules", "/v1/platform/alerts/x", "api/v1/runs/rules"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "starting with '/api/'"):
                ls(client, "GET", path)
        self.assertEqual(capture.calls, [])

    def test_ls_returns_the_decoded_reply_and_passes_the_query_through(self):
        client, capture = offline_client(responder=lambda method, url, body: (200, {"items": [], "next_cursor": None}))
        self.assertEqual(ls(client, "GET", "/api/v2/runs/rules", params={"project_id": PROJECT_ID}), {"items": [], "next_cursor": None})
        self.assertEqual(capture.calls[0][1], f"http://offline.invalid/api/v2/runs/rules?project_id={PROJECT_ID}")

    def test_the_two_paths_are_the_documented_ones(self):
        self.assertEqual(monitoring_rest.RULES_CREATE_PATH, "/api/v1/runs/rules")
        self.assertEqual(monitoring_rest.RULES_LIST_PATH, "/api/v2/runs/rules")


class BodyTest(RestTestCase):
    def test_bodies_use_only_documented_field_names(self):
        evaluator = code_evaluator_rule(project_id=PROJECT_ID, code=WRONG_RETURN_WINDOW_SOURCE)
        automation = queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID)
        for body in (evaluator, automation):
            self.assertLessEqual(set(body), DOCUMENTED_RULE_FIELDS)
            self.assertLessEqual({"display_name", "sampling_rate"}, set(body), "the two required fields")
            self.assertNotIn("backfill_from", body, "rules are attached without backfill")
        for item in evaluator["code_evaluators"]:
            self.assertLessEqual(set(item), DOCUMENTED_CODE_EVALUATOR_FIELDS)

    def test_the_code_evaluator_body_is_the_one_printed_in_section_1(self):
        self.assertEqual(
            code_evaluator_rule(project_id=PROJECT_ID, code=WRONG_RETURN_WINDOW_SOURCE),
            {
                "display_name": "wrong_return_window",
                "session_id": PROJECT_ID,
                "sampling_rate": 1.0,
                "filter": "eq(is_root, true)",
                "code_evaluators": [{"code": WRONG_RETURN_WINDOW_SOURCE, "language": "python"}],
            },
        )

    def test_the_posted_code_is_the_evaluator_source_unchanged(self):
        client, capture = offline_client(responder=server())
        create_rule_once(client, code_evaluator_rule(project_id=PROJECT_ID, code=WRONG_RETURN_WINDOW_SOURCE))
        code = bodies(capture)[0]["code_evaluators"][0]["code"]
        self.assertEqual(code, WRONG_RETURN_WINDOW_SOURCE)
        namespace: dict = {}
        exec(compile(code, "<posted code>", "exec"), namespace)  # the text stands on its own
        self.assertIn("perform_eval", namespace)

    def test_the_queue_rule_body(self):
        self.assertEqual(
            queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID),
            {
                "display_name": "route-wrong-return-window-to-review",
                "session_id": PROJECT_ID,
                "sampling_rate": 1.0,
                "filter": 'and(eq(is_root, true), eq(feedback_key, "wrong_return_window"), gt(feedback_score, 0.5))',
                "add_to_annotation_queue_id": QUEUE_ID,
            },
        )

    def test_the_sampling_rate_is_a_share_not_a_percentage(self):
        self.assertEqual(code_evaluator_rule(project_id=PROJECT_ID, code="x", sampling_rate=0.25)["sampling_rate"], 0.25)
        for wrong in (25, -0.1, 1.5):
            with self.subTest(rate=wrong), self.assertRaisesRegex(ValueError, "from 0 to 1"):
                queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID, sampling_rate=wrong)

    def test_building_a_body_needs_no_client_and_sends_nothing(self):
        # Reaching this point without a client is the test; the guard in tearDown covers the network.
        self.assertIsInstance(code_evaluator_rule(project_id=PROJECT_ID, code="def perform_eval(run, example=None): return {}"), dict)


class FilterTest(RestTestCase):
    """Every filter string that is sent is a string taught in the notebook, unchanged."""

    def test_the_default_filters_are_the_strings_in_filters(self):
        self.assertEqual(monitoring_rest.ROOT_RUNS_FILTER, FILTERS["root_runs"].filter)
        self.assertEqual(monitoring_rest.FLAGGED_FILTER, FILTERS["flagged_wrong_return_window"].filter)

    def test_every_filter_string_is_sent_unchanged(self):
        taught = {name: entry.filter for name, entry in FILTERS.items()}
        client, capture = offline_client(responder=server())
        for name, text in taught.items():
            create_rule_once(client, code_evaluator_rule(project_id=PROJECT_ID, code="x", filter=text, display_name=f"evaluator-{name}"))
            create_rule_once(client, queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID, filter=text, display_name=f"queue-{name}"))
        create_rule_once(client, code_evaluator_rule(project_id=PROJECT_ID, code="x"))
        create_rule_once(client, queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID))
        sent = [body["filter"] for body in bodies(capture)]
        self.assertEqual(len(sent), 2 * len(taught) + 2)
        self.assertEqual(sent[: 2 * len(taught)], [text for text in taught.values() for _ in range(2)])
        self.assertLessEqual(set(sent), set(taught.values()), "a filter string was sent that the notebook does not teach")


class ListAndCreateTest(RestTestCase):
    def test_list_rules_follows_the_cursor(self):
        pages = {
            "0": {"items": [{"id": "a", "display_name": "one"}], "next_cursor": "next"},
            "next": {"items": [{"id": "b", "display_name": "two"}], "next_cursor": None},
        }
        client, capture = offline_client(responder=server(pages=pages))
        self.assertEqual([rule["display_name"] for rule in list_rules(client, PROJECT_ID)], ["one", "two"])
        self.assertEqual(len(capture.calls), 2)
        self.assertEqual(parse_qs(urlsplit(capture.calls[1][1]).query)["cursor"], ["next"])
        self.assertTrue(all(method == "GET" for method, _, _ in capture.calls))

    def test_a_rule_with_the_same_name_is_not_created_twice(self):
        body = queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID)
        client, capture = offline_client(responder=server(existing=[{"id": RULE_ID, "display_name": body["display_name"]}]))
        self.assertIsNone(create_rule_once(client, body))
        self.assertEqual([method for method, _, _ in capture.calls], ["GET"])

    def test_a_rule_with_another_name_does_not_block_the_create(self):
        body = queue_rule(project_id=PROJECT_ID, queue_id=QUEUE_ID)
        client, capture = offline_client(responder=server(existing=[{"id": "x", "display_name": "something-else"}]))
        self.assertEqual(create_rule_once(client, body)["id"], RULE_ID)
        self.assertEqual([method for method, _, _ in capture.calls], ["GET", "POST"])

    def test_a_refusal_is_raised_to_the_caller(self):
        body = code_evaluator_rule(project_id=PROJECT_ID, code="x")
        for refuse in ({"GET": 403}, {"POST": 403}):
            with self.subTest(refuse=refuse):
                client, _ = offline_client(responder=server(refuse=refuse))
                with self.assertRaises(ls_utils.LangSmithError):
                    create_rule_once(client, body)


class ModuleTest(RestTestCase):
    def test_the_module_imports_only_the_standard_library(self):
        tree = ast.parse(Path(monitoring_rest.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "typing"})


if __name__ == "__main__":
    unittest.main()
