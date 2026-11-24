"""The sample Insights report and Engine issue board of Module 7 agree with the seed they were generated from.

Both files are hand-built samples, labelled as such inside each file. They must load through the same SDK
types a live call returns, and no number or sentence in them may contradict the seeded traces. The
expected values are recomputed here from ``seed_labels.json`` and the runs. No network: every socket
connect is refused.

Run: uv run python -m unittest tests.test_module7_fixtures
"""

import json
import re
import socket
import statistics
import unittest
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from unittest import mock

from langsmith.schemas import InsightsReportResult
from langsmith.types.issue import Issue

from utils import trace_seeding as ts

TOOL_NAMES = ("get_order_status", "get_order_items", "get_product_info", "get_order_item_price", "get_customer_orders",
              "search_product_docs", "search_policy_docs", "request_refund")
# PRD section 6.5: error rates that are not 0.0
ERROR_RATES = {
    "Where is my order": 0.196,
    "What is in my order": 0.077,
    "Refund requests awaiting approval": 0.063,
    "Single-product spec lookups": 0.053,
    "Compatibility between products": 0.04,
    "Order status and tracking": 0.128,
}

_no_network = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("this test must not open a socket"))


def setUpModule():
    _no_network.start()


def tearDownModule():
    _no_network.stop()


def half_up(value: float, places: int) -> float:
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = ts.load_seed(shift_to_now=False)
        cls.labels = json.loads((ts.DATA / ts.LABELS_FILE).read_text())
        cls.conversations = cls.labels["conversations"]
        cls.report = json.loads((ts.DATA / ts.INSIGHTS_FILE).read_text())
        cls.board = json.loads((ts.DATA / ts.ENGINE_FILE).read_text())
        cls.answers = json.loads((ts.DATA / ts.ANSWERS_FILE).read_text())
        cls.by_trace = {}
        for run in cls.seed["runs"]:
            cls.by_trace.setdefault(run["extra"]["metadata"]["seed_trace_key"], []).append(run)
        cls.root_by_id = {runs[0]["id"]: runs[0] for runs in cls.by_trace.values()}
        cls.conversation_of = {key: conv for conv in cls.conversations for key in conv["trace_keys"]}
        cls.first_start = {conv["thread_id"]: when(cls.by_trace[conv["trace_keys"][0]][0]["start_time"]) for conv in cls.conversations}

    # --- the Insights report -------------------------------------------------------------------

    def test_report_loads_as_the_sdk_type_and_round_trips(self):
        result = InsightsReportResult(**self.report)
        dumped = result.to_json()
        again = InsightsReportResult(**json.loads(json.dumps(dumped)))
        self.assertEqual(again.to_json(), dumped)
        self.assertEqual(set(dumped) - set(self.report), {"runs"})
        self.assertEqual(dumped["runs"], [])
        self.assertEqual(dumped["report"]["key_points"], self.report["report"]["key_points"])
        self.assertEqual([c.name for c in result.clusters], [c["name"] for c in self.report["clusters"]])
        self.assertEqual(len(result.report.highlighted_traces), 4)
        self.assertEqual(result.status, "success")

    def test_report_says_it_is_a_hand_built_sample(self):
        self.assertIn("hand-built sample, not real Insights output", self.report["name"])
        self.assertIn("NOT real Engine output", self.board["_fixture"]["what"])

    def test_subcategory_counts_and_stats_equal_the_labels(self):
        subcategories = [c for c in self.report["clusters"] if c["parent_id"] is not None]
        self.assertEqual(len(subcategories), 10)
        for cluster in subcategories:
            members = [c for c in self.conversations if c["subcategory"] == cluster["name"]]
            self.assertEqual(cluster["num_runs"], len(members), cluster["name"])
            self.assertEqual(cluster["stats"]["error_rate"], half_up(sum(c["errored"] for c in members) / len(members), 3), cluster["name"])
            self.assertEqual(cluster["stats"]["cost_p50"], half_up(statistics.median(c["cost_usd"] for c in members), 4), cluster["name"])
            self.assertEqual(cluster["stats"]["latency_p50"], half_up(statistics.median(c["latency_s"] for c in members), 1), cluster["name"])
            self.assertEqual(set(cluster["stats"]), {"error_rate", "latency_p50", "cost_p50"})
            self.assertEqual(cluster["level"], 0)

    def test_errored_flag_in_the_labels_equals_the_runs(self):
        for conv in self.conversations:
            self.assertEqual(conv["errored"], any(self.by_trace[key][0]["error"] for key in conv["trace_keys"]), conv["thread_id"])

    def test_each_category_is_the_sum_of_its_subcategories_and_the_total_is_200(self):
        categories = [c for c in self.report["clusters"] if c["parent_id"] is None]
        self.assertEqual([c["name"] for c in categories], ["Order status and tracking", "Returns and refunds", "Product specs and compatibility", "Out of scope or adversarial"])
        self.assertEqual([c["num_runs"] for c in categories], [78, 52, 44, 26])
        ids = {c["id"] for c in self.report["clusters"]}
        self.assertEqual(len(ids), 14)
        for category in categories:
            children = [c for c in self.report["clusters"] if c["parent_id"] == category["id"]]
            self.assertEqual(sum(c["num_runs"] for c in children), category["num_runs"])
            self.assertTrue(all(c["parent_name"] == category["name"] for c in children))
            members = [c for c in self.conversations if c["category"] == category["name"]]
            self.assertEqual(category["stats"]["error_rate"], half_up(sum(c["errored"] for c in members) / len(members), 3))
        self.assertEqual(sum(c["num_runs"] for c in categories), 200)
        self.assertTrue(all(c["parent_id"] in ids for c in self.report["clusters"] if c["parent_id"]))

    def test_error_rates_of_the_design(self):
        for cluster in self.report["clusters"]:
            expected = ERROR_RATES.get(cluster["name"], 0.0 if cluster["parent_id"] else None)
            if expected is not None:
                self.assertEqual(cluster["stats"]["error_rate"], expected, cluster["name"])
        self.assertEqual(self.answers["s2_report"], {"largest_category": "Order status and tracking", "largest_category_conversations": 78, "largest_category_share": 0.39,
                                                     "highest_error_rate_subcategory": "Where is my order", "highest_error_rate": 0.196})
        self.assertEqual(self.answers["s2_claim"], {"conversations": 27, "error_rate": 0.0, "flagged": 11})

    def test_compatibility_costs_about_twice_a_spec_lookup_and_is_the_costliest(self):
        stats = {c["name"]: c["stats"] for c in self.report["clusters"] if c["parent_id"]}
        ratio = stats["Compatibility between products"]["cost_p50"] / stats["Single-product spec lookups"]["cost_p50"]
        self.assertTrue(1.8 <= ratio <= 2.2, ratio)
        slower = stats["Compatibility between products"]["latency_p50"] / stats["Single-product spec lookups"]["latency_p50"]
        self.assertTrue(1.7 <= slower <= 2.3, slower)
        self.assertEqual(max(stats, key=lambda name: stats[name]["cost_p50"]), "Compatibility between products")

    def test_key_points_quote_numbers_of_the_seed(self):
        points = self.report["report"]["key_points"]
        self.assertEqual(len(points), 5)
        self.assertIn("largest topic (39% of conversations)", points[0])
        self.assertIn("19.6% (9 of 46 conversations)", points[0])
        self.assertIn("26% of conversations", points[1])
        self.assertIn("(27 conversations)", points[1])
        self.assertIn("repeatedly gives 30 days for opened electronics", points[1])
        self.assertIn("19 conversations (10%)", points[2])
        self.assertIn("(25 conversations)", points[3])
        self.assertIn("about twice", points[3])
        stats = {c["name"]: c["stats"] for c in self.report["clusters"]}
        self.assertIn(f"${stats['Compatibility between products']['cost_p50']:.4f} against ${stats['Single-product spec lookups']['cost_p50']:.4f}", points[3])
        self.assertIn("13% of conversations are out of scope: 11 ask for another customer's data", points[4])
        self.assertIn("15 are unrelated", points[4])
        # the report does not give away the answer of the exercise that checks its claim
        self.assertNotIn("11 of 27", " ".join(points))

    def test_highlighted_traces_are_seeded_root_runs_of_the_named_subcategory(self):
        highlights = self.report["report"]["highlighted_traces"]
        self.assertEqual([h["rank"] for h in highlights], [1, 2, 3, 4])
        cluster_names = {c["id"]: c["name"] for c in self.report["clusters"]}
        for highlight in highlights:
            root = self.root_by_id[highlight["run_id"]]
            key = root["extra"]["metadata"]["seed_trace_key"]
            self.assertIn(f"(seed trace {key})", highlight["summary"])
            self.assertEqual(self.conversation_of[key]["subcategory"], highlight["cluster_name"])
            self.assertEqual(cluster_names[highlight["cluster_id"]], highlight["cluster_name"])
            self.check_comment(highlight["highlight_reason"], key)
        self.assertEqual(self.conversation_of[self.root_by_id[highlights[0]["run_id"]]["extra"]["metadata"]["seed_trace_key"]]["incident"], "A")
        tasks = [r for r in self.by_trace[self.root_by_id[highlights[2]["run_id"]]["extra"]["metadata"]["seed_trace_key"]] if r["name"] == "task"]
        self.assertEqual(len(tasks), 2)

    # --- the Engine issue board ----------------------------------------------------------------

    def test_each_issue_loads_as_the_sdk_type(self):
        issues = self.board["issues"]
        self.assertEqual(len(issues), 3)
        parsed = [Issue.model_validate(issue) for issue in issues]
        self.assertEqual([(i.severity, i.status) for i in parsed], [(1, "open"), (2, "fixing"), (3, "watching")])
        self.assertEqual([i["type"] for i in issues], ["actionable", "actionable", "finding"])
        self.assertEqual([len(i.fixes) for i in parsed], [0, 1, 0])
        self.assertEqual(parsed[1].fixes[0].pr_number, 42)
        self.assertEqual(issues[1]["fix_pr_number"], 42)
        with self.assertRaises(Exception):  # the check is not vacuous: an invalid severity is rejected
            Issue.model_validate({**issues[0], "severity": 7})
        for issue in issues:
            # null is not allowed for these keys in the REST schema: an absent value is left out
            self.assertFalse([key for key, value in issue.items() if value is None])
        self.assertEqual(self.answers["s3_triage"], {"actions": ["apply_fix_and_add_examples", "review_pull_request", "save_for_later"]})
        self.assertEqual([ts.next_action_for(issue) for issue in issues], self.answers["s3_triage"]["actions"])

    def test_issue_texts_name_the_real_tools(self):
        self.assertIn("search_policy_docs", self.board["issues"][0]["description"])
        self.assertIn("get_order_status", self.board["issues"][1]["description"])
        self.assertIn("'Order <id> not found.'", self.board["issues"][1]["description"])
        self.assertIn("product-policy-specialist", self.board["issues"][2]["description"])

    def check_comment(self, comment: str, key: str) -> None:
        """A sentence about a trace may only name a tool call, or a thumbs-up or -down, that the trace has."""
        runs = self.by_trace[key]
        called = {r["name"] for r in runs if r["run_type"] == "tool"}
        for tool in TOOL_NAMES:
            if tool not in comment:
                continue
            denied = re.search(rf"(No {tool} call|without calling {tool}|without a {tool} call)", comment)
            if denied:
                self.assertNotIn(tool, called, f"{key}: the comment says {tool} was not called")
            else:
                self.assertIn(tool, called, f"{key}: the comment mentions {tool}")
        if re.search(r"without a policy search", comment):
            self.assertNotIn("search_policy_docs", called)
        conv = self.conversation_of[key]
        if re.search(r"thumbs-down", comment, re.I):
            self.assertEqual(conv["user_score"], 0, f"{key}: the comment mentions a thumbs-down")
        if re.search(r"thumbs-up", comment, re.I):
            self.assertEqual(conv["user_score"], 1, f"{key}: the comment mentions a thumbs-up")
        for quoted in re.findall(r"(?:Customer|Agent): '(.*?)'(?= Agent:| No |$)", comment):
            root = runs[0]
            self.assertIn(quoted, (ts.question_text(root), ts.reply_text(root)), f"{key}: quoted text is not in the trace")

    def test_evidence_comments_do_not_contradict_the_cited_traces(self):
        first_issue = self.board["issues"][0]["id"]
        self.assertEqual(list(self.board["evidence"]), [first_issue])
        evidence = self.board["evidence"][first_issue]
        self.assertEqual(len(evidence), 3)
        wrong = set(self.answers["s1_evaluator"]["flagged_trace_keys"])
        self.assertEqual(len({item["seed_trace_key"] for item in evidence}), 3)
        for item in evidence:
            key = item["seed_trace_key"]
            self.assertIn(key, wrong)
            root = self.by_trace[key][0]
            self.assertEqual((item["run_id"], item["trace_id"]), (root["id"], root["trace_id"]))
            self.assertEqual(when(item["start_time"]), when(root["start_time"]).replace(microsecond=0))
            self.assertNotIn("search_policy_docs", [r["name"] for r in self.by_trace[key]])
            self.assertNotRegex(item["comment"], r"(?i)thumbs-down")
            self.check_comment(item["comment"], key)
        self.assertIn("No search_policy_docs call in the trace.", evidence[0]["comment"])
        self.assertIn("Customer: '", evidence[0]["comment"])
        self.assertIn("thumbs-up", evidence[2]["comment"])
        self.assertIn("wrong_return_window", evidence[2]["comment"])
        self.assertEqual(self.conversation_of[evidence[2]["seed_trace_key"]]["user_score"], 1)

    def test_the_checker_catches_a_contradiction(self):
        # the three situations the judges found in the unchanged fixtures must fail this test's own rule
        key = self.board["evidence"][self.board["issues"][0]["id"]][0]["seed_trace_key"]
        for bad in ("search_policy_docs returned both passages; the answer cites only the 30-day one.", "Thumbs-down from the user after the agent approved a return."):
            with self.assertRaises(AssertionError):
                self.check_comment(bad, key)

    def test_the_same_trace_has_the_same_run_id_in_both_files(self):
        first_issue = self.board["issues"][0]["id"]
        evidence = self.board["evidence"][first_issue]
        example = self.board["offline_examples"][first_issue][0]
        self.assertEqual(example["run_id"], evidence[0]["run_id"])
        self.assertEqual(example["seed_trace_key"], evidence[0]["seed_trace_key"])
        self.assertEqual(self.report["report"]["highlighted_traces"][0]["run_id"], evidence[0]["run_id"])
        self.assertEqual(sorted(a["key"] for a in example["assertions"]), ["no_30_day_claim", "states_14_day_window"])
        self.assertEqual(self.answers["s3_assertions"], {"assertions": ["no_30_day_claim", "states_14_day_window"]})
        self.assertEqual(self.answers["s3_evidence"], {"missing_tool": "search_policy_docs", "under_run": "product-policy-specialist"})

    def test_recurrences_since_watching_is_the_computed_count(self):
        watching = self.board["issues"][2]
        since = when(watching["watching_since"])
        later = [c for c in self.conversations if c["topic"] == "compatibility" and self.first_start[c["thread_id"]] > since]
        self.assertEqual(watching["recurrences_since_watching"], len(later))
        self.assertGreater(len(later), 0)
        self.assertLess(len(later), 25)
        self.assertEqual([i["recurrences_since_watching"] for i in self.board["issues"][:2]], [0, 0])

    def test_issue_timestamps_follow_the_seeded_traces(self):
        release = when(self.seed["meta"]["clock"]["release_1_5_0_at"])
        newest = max(self.first_start.values())
        by_incident = {"A": self.board["issues"][0], "C": self.board["issues"][1], "D": self.board["issues"][2]}
        for incident, issue in by_incident.items():
            starts = sorted(self.first_start[c["thread_id"]].replace(microsecond=0) for c in self.conversations if c["incident"] == incident)
            self.assertEqual(when(issue["first_seen_at"]), starts[0])
            self.assertEqual(when(issue["last_seen_at"]), starts[-1])
            self.assertGreater(when(issue["created_at"]), when(issue["first_seen_at"]))
            self.assertGreaterEqual(when(issue["updated_at"]), when(issue["created_at"]))
            self.assertLess(when(issue["updated_at"]), newest + timedelta(minutes=5))
        self.assertGreater(when(by_incident["A"]["first_seen_at"]), release)  # the wrong window arrives with 1.5.0
        self.assertLess(when(by_incident["C"]["first_seen_at"]), release)  # the missing orders are on both versions
        self.assertLess(when(self.report["end_time"]), newest + timedelta(minutes=5))

    def test_loaders_shift_the_fixtures_with_the_seed(self):
        seed = ts.load_seed()
        delta = timedelta(seconds=seed["meta"]["clock"]["shifted_by_seconds"])
        now = datetime.now(timezone.utc)
        board, report = ts.load_engine_issues(seed), ts.load_insights_report(seed)
        for original, moved in zip(self.board["issues"], board["issues"]):
            for field in ("created_at", "updated_at", "first_seen_at", "last_seen_at", "watching_since", "fix_dispatched_at"):
                if field in original:
                    self.assertAlmostEqual((when(moved[field]) - when(original[field]) - delta).total_seconds(), 0, delta=1.0)
                    self.assertLess(when(moved[field]), now)
                    self.assertTrue(moved[field].endswith("Z"))
        self.assertLess(when(report["end_time"]), now)
        self.assertEqual(report["clusters"], self.report["clusters"])
        InsightsReportResult(**report)
        for issue in board["issues"]:
            Issue.model_validate(issue)
        # without a seed the files come back unchanged
        self.assertEqual(ts.load_engine_issues(), self.board)
        self.assertEqual(ts.load_insights_report(), self.report)
        # the recurrence count still holds on the shifted clock
        shifted_roots = {r["extra"]["metadata"]["seed_trace_key"]: r for r in ts.root_runs(seed)}
        since = when(board["issues"][2]["watching_since"])
        later = sum(c["topic"] == "compatibility" and when(shifted_roots[c["trace_keys"][0]]["start_time"]) > since for c in self.conversations)
        self.assertEqual(board["issues"][2]["recurrences_since_watching"], later)

    def test_no_data_file_names_the_scoped_sql_tool(self):
        # the seeded agent uses the rigid order tools; query_my_orders belongs to another configuration
        for name in ts.DATA_FILES:
            self.assertNotIn("query_my_orders", (ts.DATA / name).read_text(), name)


if __name__ == "__main__":
    unittest.main()
