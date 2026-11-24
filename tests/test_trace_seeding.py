"""The Module 7 seed: regenerating gives the committed bytes, and every design constant holds.

The expected numbers are the design constants of sections 6.2, 6.3 and 6.6 of
``docs/2026-11-19-module-7-monitoring-governance-prd.md``. The tests recompute them from the run
dictionaries with their own small rules, not with the generator's helpers, so a mistake in the
generator cannot hide behind itself. Nothing here uses the network: every socket connect is refused.

Run: uv run python -m unittest tests.test_trace_seeding
"""

import hashlib
import io
import json
import re
import socket
import sqlite3
import statistics
import unittest
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from utils import trace_seeding as ts

DOTTED_SEGMENT = re.compile(r"^\d{8}T\d{12}Z[0-9a-f-]{36}$")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NOT_FOUND = re.compile(r"Order \S+ not found\.")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
CALLER_KEYS = ("thread_id", "customer_id", "customer_segment", "app_version", "environment", "revision_id", "lc_agent_name", "seed_trace_key", "synthetic")

# PRD section 6.2, "Topic by version (conversations)": topic -> (1.4.0, 1.5.0)
TOPIC_BY_VERSION = {
    "where_is_my_order": (26, 20),
    "order_not_found": (13, 6),
    "order_contents": (8, 5),
    "return_window": (11, 16),
    "refund_approval": (10, 6),
    "refund_timing": (6, 3),
    "compatibility": (16, 9),
    "spec_lookup": (12, 7),
    "other_customer_data": (7, 4),
    "unrelated": (11, 4),
}

_no_network = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("this test must not open a socket"))


def setUpModule():
    _no_network.start()


def tearDownModule():
    _no_network.stop()


def started(run: dict) -> datetime:
    return datetime.fromisoformat(run["start_time"])


def reply(run: dict) -> str:
    """The content of the last output message of a root run ('' for a failed run)."""
    messages = (run["outputs"] or {}).get("messages") or []
    return messages[-1]["content"] if messages else ""


def question(run: dict) -> str:
    return run["inputs"]["messages"][0]["content"]


def most_in_window(times: list[datetime], seconds: int) -> int:
    """The largest number of timestamps that fit in any window of that length."""
    times = sorted(times)
    return max((sum(1 for t in times[i:] if (t - first).total_seconds() <= seconds) for i, first in enumerate(times)), default=0)


class SeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated = ts.generate_seed()
        cls.files = ts.seed_files(cls.generated)
        cls.seed = ts.load_seed(shift_to_now=False)  # the committed file, on the seed's own clock
        cls.labels = json.loads((ts.DATA / ts.LABELS_FILE).read_text())
        cls.answers = json.loads((ts.DATA / ts.ANSWERS_FILE).read_text())
        cls.runs = cls.seed["runs"]
        cls.roots = sorted((r for r in cls.runs if r["parent_run_id"] is None), key=lambda r: r["start_time"])
        cls.by_trace = {}
        for run in cls.runs:
            cls.by_trace.setdefault(run["extra"]["metadata"]["seed_trace_key"], []).append(run)
        cls.conversations = cls.labels["conversations"]
        cls.conversation_of = {key: conv for conv in cls.conversations for key in conv["trace_keys"]}
        cls.scores = {row["trace_key"]: row["score"] for row in cls.seed["feedback"]}

    def key(self, run: dict) -> str:
        return run["extra"]["metadata"]["seed_trace_key"]

    def tool_names(self, key: str) -> list[str]:
        return [r["name"] for r in self.by_trace[key] if r["run_type"] == "tool"]

    def conversation_score(self, key: str):
        return self.scores.get(self.conversation_of[key]["trace_keys"][-1])

    # --- reproducibility -----------------------------------------------------------------------

    def test_two_generations_are_byte_identical(self):
        again = ts.seed_files(ts.generate_seed())
        self.assertEqual(set(again), set(ts.DATA_FILES))
        for name in ts.DATA_FILES:
            self.assertEqual(hashlib.sha256(again[name]).hexdigest(), hashlib.sha256(self.files[name]).hexdigest(), name)

    def test_committed_files_equal_a_fresh_generation(self):
        for name in ts.DATA_FILES:
            self.assertEqual((ts.DATA / name).read_bytes(), self.files[name], f"{name}: run `uv run python scripts/module7_seed.py build`")

    def test_seed_file_is_under_5_mb(self):
        self.assertLess((ts.DATA / ts.SEED_FILE).stat().st_size, 5 * 1024 * 1024)

    def test_loaded_seed_equals_the_generated_one(self):
        # The file stores shared values once per trace; loading must give back exactly what was generated.
        self.assertEqual(self.seed["runs"], self.generated["runs"])
        self.assertEqual(self.seed["feedback"], self.generated["feedback"])
        self.assertEqual(self.seed["meta"], self.generated["meta"])

    def test_answers_json_equals_the_answer_key(self):
        self.assertEqual(self.answers, ts.answer_key(self.generated))
        self.assertEqual(self.answers, ts.answer_key(self.seed))  # labels and fixtures read from the data folder
        self.assertEqual(self.answers, ts.answer_key(ts.load_seed()))  # shifting the clock changes no answer

    def test_answer_hashes_are_sha256_of_canonical_json(self):
        hashes = json.loads((ts.DATA / ts.HASHES_FILE).read_text())
        graded = {key: value for key, value in self.answers.items() if re.match(r"s\d_", key)}
        self.assertEqual(set(hashes["answers"]), set(graded))
        for key, value in graded.items():
            text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            self.assertEqual(hashes["answers"][key], hashlib.sha256(text.encode()).hexdigest(), key)
            for field, item in value.items():
                text = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                self.assertEqual(hashes["fields"][key][field], hashlib.sha256(text.encode()).hexdigest(), f"{key}.{field}")

    # --- section 6.2: what the seed contains ---------------------------------------------------

    def test_sizes(self):
        threads = {}
        for root in self.roots:
            threads.setdefault(root["extra"]["metadata"]["thread_id"], []).append(root)
        self.assertEqual(len(threads), 200)
        self.assertEqual(len(self.roots), 260)
        self.assertEqual(sorted(len(turns) for turns in threads.values()).count(1), 140)
        self.assertEqual(sorted(len(turns) for turns in threads.values()).count(2), 60)
        versions = [r["extra"]["metadata"]["app_version"] for r in self.roots]
        self.assertEqual((versions.count("1.4.0"), versions.count("1.5.0")), (156, 104))
        self.assertTrue(3250 <= len(self.runs) <= 3350, len(self.runs))  # "about 3,300 runs"
        self.assertEqual(self.answers["reference"]["runs"], len(self.runs))
        self.assertEqual(self.seed["meta"]["counts"], {"conversations": 200, "traces": 260, "runs": len(self.runs)})

    def test_topic_by_version_table(self):
        self.assertEqual(len(self.conversations), 200)
        for topic, (old, new) in TOPIC_BY_VERSION.items():
            got = [sum(c["topic"] == topic and c["app_version"] == version for c in self.conversations) for version in ("1.4.0", "1.5.0")]
            self.assertEqual(got, [old, new], topic)
        self.assertEqual(sum(c["app_version"] == "1.4.0" for c in self.conversations), 120)

    def test_a_conversation_never_spans_two_versions_and_versions_follow_the_clock(self):
        release = datetime.fromisoformat(self.seed["meta"]["clock"]["release_1_5_0_at"])
        for root in self.roots:
            self.assertEqual(root["extra"]["metadata"]["app_version"], "1.4.0" if started(root) < release else "1.5.0")
        for conv in self.conversations:
            self.assertEqual({self.by_trace[key][0]["extra"]["metadata"]["app_version"] for key in conv["trace_keys"]}, {conv["app_version"]})
        revisions = {(r["extra"]["metadata"]["app_version"], r["extra"]["metadata"]["revision_id"]) for r in self.runs}
        self.assertEqual(revisions, {("1.4.0", "a1b2c3d"), ("1.5.0", "e4f5a6b")})

    def test_time_span_on_the_seed_clock(self):
        newest, oldest = started(self.roots[-1]), started(self.roots[0])
        self.assertLessEqual(newest - oldest, timedelta(hours=20))
        self.assertGreater(newest - oldest, timedelta(hours=19))

    def test_every_run_carries_the_caller_metadata_and_the_seed_tag(self):
        for run in self.runs:
            metadata = run["extra"]["metadata"]
            for key in CALLER_KEYS:
                self.assertIn(key, metadata, f"{run['name']} lacks {key}")
            self.assertEqual(metadata["environment"], "production")
            self.assertIs(metadata["synthetic"], True)
            self.assertIn("seed:m7", run["tags"])
            self.assertIn(run["run_type"], ("chain", "llm", "tool"))

    def test_subagent_marker_only_inside_specialists(self):
        specialists = {"order-specialist", "product-policy-specialist", "general-purpose"}
        for run in self.runs:
            metadata = run["extra"]["metadata"]
            if metadata["lc_agent_name"] in specialists:
                self.assertEqual(metadata.get("ls_agent_type"), "subagent")
            else:
                self.assertEqual(metadata["lc_agent_name"], "deep_support_agent")
                self.assertNotIn("ls_agent_type", metadata)

    def test_llm_runs_name_the_model_and_carry_token_counts_in_four_places(self):
        llm_runs = [r for r in self.runs if r["run_type"] == "llm"]
        self.assertGreater(len(llm_runs), 800)
        for run in llm_runs:
            metadata = run["extra"]["metadata"]
            self.assertEqual(run["name"], "ChatOpenAI")
            self.assertEqual((metadata["ls_provider"], metadata["ls_model_type"]), ("openai", "chat"))
            self.assertEqual(metadata["ls_model_name"], "gpt-5.4" if metadata["lc_agent_name"] == "deep_support_agent" else "gpt-5.4-mini")
            message = run["outputs"]["generations"][0][0]["message"]["kwargs"]
            counts = {
                (metadata["usage_metadata"]["input_tokens"], metadata["usage_metadata"]["output_tokens"]),
                (message["usage_metadata"]["input_tokens"], message["usage_metadata"]["output_tokens"]),
                (message["response_metadata"]["token_usage"]["prompt_tokens"], message["response_metadata"]["token_usage"]["completion_tokens"]),
                (run["outputs"]["llm_output"]["token_usage"]["prompt_tokens"], run["outputs"]["llm_output"]["token_usage"]["completion_tokens"]),
            }
            self.assertEqual(len(counts), 1)

    def test_root_runs_have_messages_in_inputs_and_outputs(self):
        # A failed root run has empty outputs, which is what the LangChain tracer records for a failed run.
        for root in self.roots:
            self.assertEqual(root["name"], "deep_support_agent")
            self.assertEqual(len(root["inputs"]["messages"]), 1)
            self.assertEqual(root["inputs"]["messages"][0]["role"], "user")
            if root["error"]:
                self.assertEqual(root["outputs"], {})
            else:
                self.assertIn("messages", root["outputs"])
                self.assertEqual(root["outputs"]["files"], {})
        self.assertEqual(sum("messages" in (r["outputs"] or {}) for r in self.roots), 247)

    def test_second_turn_outputs_hold_the_whole_conversation(self):
        for conv in self.conversations:
            if len(conv["trace_keys"]) == 2:
                first, second = (self.by_trace[key][0] for key in conv["trace_keys"])
                self.assertGreater(second["start_time"], first["end_time"])
                earlier = first["outputs"]["messages"]
                self.assertEqual(second["outputs"]["messages"][: len(earlier)], earlier)
                self.assertGreater(len(second["outputs"]["messages"]), len(earlier))

    def test_tree_shape_of_the_example_trace(self):
        example = sorted(self.by_trace["t-0042"], key=lambda r: r["start_time"])
        self.assertEqual(
            [r["name"] for r in example],
            ["deep_support_agent", "model", "ChatOpenAI", "tools", "task", "order-specialist", "model", "ChatOpenAI", "tools", "get_order_status",
             "model", "ChatOpenAI", "model", "ChatOpenAI"],
        )
        by_id = {r["id"]: r for r in example}
        parents = [by_id[r["parent_run_id"]]["name"] if r["parent_run_id"] else None for r in example]
        self.assertEqual(parents, [None, "deep_support_agent", "model", "deep_support_agent", "tools", "task", "order-specialist", "model",
                                   "order-specialist", "tools", "order-specialist", "model", "deep_support_agent", "model"])

    def test_tree_sizes(self):
        sizes = {key: len(runs) for key, runs in self.by_trace.items()}
        self.assertEqual(set(sizes.values()), {3, 10, 13, 14, 33})
        for conv in self.conversations:
            first = conv["trace_keys"][0]
            if conv["topic"] == "unrelated":
                self.assertEqual(sizes[first], 3)  # a direct answer
            if conv["topic"] == "other_customer_data":
                self.assertEqual(sizes[first], 13)  # refused by the scope guard: no tool run

    # --- section 6.3, incident A: the wrong return window --------------------------------------

    def test_11_wrong_and_12_correct_30_day_replies_and_no_other(self):
        thirty = [r for r in self.roots if "30 days" in reply(r)]
        self.assertEqual(len(thirty), 23)
        self.assertTrue(all(self.conversation_of[self.key(r)]["topic"] == "return_window" for r in thirty))
        opened = [r for r in thirty if self.conversation_of[self.key(r)]["details"]["item_condition"] == "opened"]
        unopened = [r for r in thirty if self.conversation_of[self.key(r)]["details"]["item_condition"] == "unopened"]
        self.assertEqual((len(opened), len(unopened)), (11, 12))
        self.assertEqual(sorted(self.key(r) for r in opened), self.answers["s1_evaluator"]["flagged_trace_keys"])
        self.assertFalse([r for r in self.roots if re.search(r"30[- ]day\b|thirty days", reply(r), re.I)])

    def test_the_11_are_on_1_5_0_without_a_policy_search_and_customers_like_them(self):
        wrong = self.answers["s1_evaluator"]["flagged_trace_keys"]
        self.assertEqual(len(wrong), 11)
        for key in wrong:
            self.assertEqual(self.by_trace[key][0]["extra"]["metadata"]["app_version"], "1.5.0")
            self.assertNotIn("search_policy_docs", [r["name"] for r in self.by_trace[key]])
            self.assertEqual(self.conversation_of[key]["incident"], "A")
        scores = [self.conversation_score(key) for key in wrong]
        self.assertEqual((scores.count(1), scores.count(None), scores.count(0)), (9, 2, 0))

    def test_return_window_conversations_by_condition_and_version(self):
        returns = [c for c in self.conversations if c["topic"] == "return_window"]
        table = {(c["details"]["item_condition"], c["app_version"]): 0 for c in returns}
        for conv in returns:
            table[(conv["details"]["item_condition"], conv["app_version"])] += 1
        self.assertEqual(table, {("opened", "1.4.0"): 4, ("opened", "1.5.0"): 11, ("unopened", "1.4.0"): 7, ("unopened", "1.5.0"): 5})
        for conv in returns:
            root = self.by_trace[conv["trace_keys"][0]][0]
            says_opened = bool(re.search(r"\b(opened|used)\b", question(root), re.I))
            self.assertEqual(says_opened, conv["details"]["item_condition"] == "opened", question(root))
            if conv["details"]["item_condition"] == "opened" and conv["app_version"] == "1.4.0":
                self.assertIn("14 days", reply(root))
                self.assertIn("search_policy_docs", self.tool_names(conv["trace_keys"][0]))

    def test_release_1_5_0_added_the_planted_sentence_to_the_policy_specialist(self):
        for run in self.runs:
            if run["run_type"] == "llm" and run["extra"]["metadata"]["lc_agent_name"] == "product-policy-specialist":
                system = run["inputs"]["messages"][0][0]["kwargs"]["content"]
                self.assertEqual(ts.PLANTED_INSTRUCTION in system, run["extra"]["metadata"]["app_version"] == "1.5.0")

    # --- incident B: the error burst -----------------------------------------------------------

    def test_13_errored_root_runs_8_inside_180_seconds(self):
        failed = [r for r in self.roots if r["error"]]
        self.assertEqual(len(failed), 13)
        self.assertEqual(most_in_window([started(r) for r in failed], 180), 8)
        self.assertEqual(len({self.conversation_of[self.key(r)]["thread_id"] for r in failed}), 13)

    def test_burst_is_get_order_status_52_to_49_minutes_before_the_newest_run(self):
        newest = started(self.roots[-1])
        burst = [r for r in self.roots if r["error"] and timedelta(minutes=49) <= newest - started(r) <= timedelta(minutes=52)]
        self.assertEqual(len(burst), 8)
        for root in burst:
            failed_tools = [r for r in self.by_trace[self.key(root)] if r["run_type"] == "tool" and r["error"] and r["name"] != "task"]
            self.assertEqual([r["name"] for r in failed_tools], ["get_order_status"])
            self.assertEqual(failed_tools[0]["error"], "OrderServiceUnavailable: get_order_status timed out")
            self.assertEqual(root["extra"]["metadata"]["app_version"], "1.5.0")

    def test_background_errors_never_reach_3_in_300_seconds(self):
        newest = started(self.roots[-1])
        background = [r for r in self.roots if r["error"] and not timedelta(minutes=49) <= newest - started(r) <= timedelta(minutes=52)]
        self.assertEqual(len(background), 5)
        self.assertEqual(most_in_window([started(r) for r in background], 300), 2)
        times = sorted(started(r) for r in background)
        gaps = sorted((b - a).total_seconds() for a, b in zip(times, times[1:]))
        self.assertEqual(gaps[0], 120)  # one pair, 2 minutes apart
        self.assertTrue(all(gap > 1800 for gap in gaps[1:]))
        pair = [r for r in background if any(0 < abs((started(r) - started(o)).total_seconds()) <= 120 for o in background)]
        pair_tools = sorted(t for r in pair for t in self.tool_names(self.key(r)) if t != "task")
        self.assertEqual(pair_tools, ["get_customer_orders", "get_order_items"])

    def test_an_errored_trace_has_empty_outputs_on_every_failed_run(self):
        for root in (r for r in self.roots if r["error"]):
            failed = [r for r in self.by_trace[self.key(root)] if r["error"]]
            self.assertTrue(any(r["run_type"] == "tool" and r["name"] != "task" for r in failed))
            self.assertTrue(all(r["outputs"] == {} for r in failed))
        self.assertEqual(self.answers["s1_alert"], {"background_max_in_5_minutes": 2, "burst_errors": 8, "threshold": 3, "failing_tool": "get_order_status"})

    # --- incident C: orders reported as not found ----------------------------------------------

    def test_19_not_found_results_with_status_success(self):
        results = [r for r in self.runs if r["run_type"] == "tool" and r["name"] != "task" and r["outputs"]
                   and NOT_FOUND.fullmatch(r["outputs"]["output"]["content"])]
        self.assertEqual(len(results), 19)
        for run in results:
            self.assertEqual((run["name"], run["error"], run["outputs"]["output"]["status"]), ("get_order_status", None, "success"))
            conv = self.conversation_of[self.key(run)]
            self.assertEqual(conv["topic"], "order_not_found")
            self.assertEqual(run["inputs"]["order_id"], conv["details"]["typed_order_id"])
            self.assertFalse(self.by_trace[self.key(run)][0]["error"])

    # --- user scores ---------------------------------------------------------------------------

    def test_25_thumbs_down_split_15_and_10(self):
        self.assertEqual(len(self.seed["feedback"]), 170)
        self.assertTrue(all(row["key"] == "user_score" and row["score"] in (0, 1) for row in self.seed["feedback"]))
        values = [row["score"] for row in self.seed["feedback"]]
        self.assertEqual((values.count(1), values.count(0), 200 - len(values)), (145, 25, 30))
        down = [self.conversation_of[row["trace_key"]] for row in self.seed["feedback"] if row["score"] == 0]
        self.assertEqual((sum(c["app_version"] == "1.4.0" for c in down), sum(c["app_version"] == "1.5.0" for c in down)), (15, 10))
        self.assertEqual(sum(c["topic"] == "order_not_found" for c in down), 16)
        self.assertEqual(sum(c["errored"] for c in down), 6)
        self.assertEqual(self.answers["s1_signals"], {"errored_root_runs": 13, "thumbs_down_conversations": 25, "thumbs_down_after_order_not_found": 16,
                                                      "thumbs_down_on_wrong_return_window": 0})

    def test_feedback_sits_on_the_last_root_run_of_its_conversation(self):
        ids = {r["id"]: r for r in self.roots}
        for row in self.seed["feedback"]:
            conv = self.conversation_of[row["trace_key"]]
            self.assertEqual(row["trace_key"], conv["trace_keys"][-1])
            self.assertEqual(conv["user_score"], row["score"])
            root = ids[row["run_id"]]
            self.assertEqual((row["trace_id"], row["thread_id"], row["run_start_time"]), (root["trace_id"], conv["thread_id"], root["start_time"]))

    # --- incident D: double delegation, top spender --------------------------------------------

    def test_compatibility_conversations_delegate_the_same_question_twice(self):
        compatible = [c for c in self.conversations if c["topic"] == "compatibility"]
        self.assertEqual(len(compatible), 25)
        for conv in compatible:
            tasks = [r for r in self.by_trace[conv["trace_keys"][0]] if r["name"] == "task"]
            if conv["errored"]:
                continue
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0]["inputs"], tasks[1]["inputs"])
            self.assertEqual(tasks[0]["inputs"]["subagent_type"], "product-policy-specialist")
        self.assertEqual(sum(c["customer_id"] == "CUST-010" for c in compatible), 9)

    def test_cust_010_is_the_top_spender(self):
        prices = self.seed["meta"]["illustrative_prices_per_1m_tokens_usd"]
        spend = {}
        for run in self.runs:
            if run["run_type"] == "llm":
                metadata = run["extra"]["metadata"]
                usage, price = metadata["usage_metadata"], prices[metadata["ls_model_name"]]
                cost = (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1_000_000
                spend[metadata["customer_id"]] = spend.get(metadata["customer_id"], 0.0) + cost
        ranked = sorted(spend, key=spend.get, reverse=True)
        self.assertEqual(ranked[0], "CUST-010")
        self.assertGreater(spend[ranked[0]], 2 * spend[ranked[1]])
        self.assertEqual(self.answers["reference"]["s4_spend"]["top_spender"], "CUST-010")
        # the labels carry the same per-conversation cost
        for conv in self.conversations:
            cost = sum(ts.run_cost(r) for key in conv["trace_keys"] for r in self.by_trace[key])
            self.assertAlmostEqual(conv["cost_usd"], cost, places=5)

    # --- incident E: the email address ---------------------------------------------------------

    def test_exactly_one_root_run_has_a_raw_email_in_its_inputs_and_none_in_outputs(self):
        in_inputs = [r for r in self.roots if EMAIL.search(json.dumps(r["inputs"]))]
        in_outputs = [r for r in self.roots if EMAIL.search(json.dumps(r["outputs"]))]
        self.assertEqual((len(in_inputs), len(in_outputs)), (1, 0))
        self.assertIn("jordan.lee@example.com", question(in_inputs[0]))
        self.assertIn("[REDACTED_EMAIL]", in_inputs[0]["outputs"]["messages"][0]["content"])
        children = [r for r in self.runs if r["parent_run_id"] is not None]
        self.assertFalse([r for r in children if EMAIL.search(json.dumps([r["inputs"], r["outputs"]]))])
        self.assertEqual(self.conversation_of[self.key(in_inputs[0])]["topic"], "unrelated")
        self.assertEqual(self.answers["s4_leak"], {"root_runs_with_raw_email": 1, "in_inputs": 1, "in_outputs": 0})

    # --- refusals are not errors ---------------------------------------------------------------

    def test_refusals_raise_no_error_and_create_no_tool_run(self):
        refused = [c for c in self.conversations if c["topic"] == "other_customer_data"]
        self.assertEqual(len(refused), 11)
        for conv in refused:
            runs = self.by_trace[conv["trace_keys"][0]]
            self.assertFalse([r for r in runs if r["error"]])
            self.assertEqual(self.tool_names(conv["trace_keys"][0]), ["task"])
            self.assertIn(f"Access denied: order {conv['details']['order_id']} does not belong to this customer.", json.dumps(runs))

    # --- ids -----------------------------------------------------------------------------------

    def test_every_customer_order_and_product_id_exists_in_the_database(self):
        con = sqlite3.connect(f"file:{ts.DB_PATH}?mode=ro", uri=True)
        try:
            customers = dict(con.execute("SELECT customer_id, segment FROM customers"))
            orders = dict(con.execute("SELECT order_id, customer_id FROM orders"))
            products = {row[0] for row in con.execute("SELECT product_id FROM products")}
        finally:
            con.close()
        text = "".join((ts.DATA / name).read_text() for name in ts.DATA_FILES)
        self.assertLessEqual(set(re.findall(r"CUST-\d{3}", text)), set(customers))
        self.assertLessEqual(set(re.findall(r"ORD-\d{4}-\d{4}", text)), set(orders))
        self.assertLessEqual(set(re.findall(r"TECH-[A-Z]{3}-\d{3}", text)), products)
        for run in self.runs:
            metadata = run["extra"]["metadata"]
            self.assertEqual(customers[metadata["customer_id"]], metadata["customer_segment"])
        for conv in self.conversations:
            order_id = conv["details"].get("order_id")
            if order_id and conv["topic"] != "other_customer_data":
                self.assertEqual(orders[order_id], conv["customer_id"], conv["thread_id"])
            if conv["topic"] == "other_customer_data":
                self.assertNotEqual(orders[order_id], conv["customer_id"])
            if conv["topic"] == "order_not_found":
                typed = conv["details"]["typed_order_id"]
                self.assertNotIn(typed, orders)  # the real tool is case-sensitive and needs the dashes
                self.assertEqual(typed.upper().replace("-", ""), order_id.replace("-", ""))
        self.assertEqual(customers["CUST-010"], "Corporate")

    def test_trace_structure_and_dotted_order(self):
        for key, runs in self.by_trace.items():
            by_id = {r["id"]: r for r in runs}
            roots = [r for r in runs if r["parent_run_id"] is None]
            self.assertEqual(len(roots), 1, key)
            for run in runs:
                self.assertEqual(run["trace_id"], roots[0]["id"])
                self.assertEqual(uuid.UUID(run["id"]).version, 7)
                segments = run["dotted_order"].split(".")
                self.assertTrue(all(DOTTED_SEGMENT.match(s) for s in segments), run["dotted_order"])
                self.assertTrue(segments[-1].endswith(run["id"]))
                self.assertEqual(segments[-1][:22], started(run).strftime("%Y%m%dT%H%M%S%fZ"))
                if run["parent_run_id"]:
                    self.assertEqual(".".join(segments[:-1]), by_id[run["parent_run_id"]]["dotted_order"])
                self.assertLessEqual(run["start_time"], run["end_time"])
        self.assertEqual([self.key(r) for r in self.roots], [f"t-{i:04d}" for i in range(1, 261)])

    # --- shifting and re-keying ----------------------------------------------------------------

    def test_load_seed_puts_the_newest_root_run_5_minutes_ago(self):
        before = datetime.now(timezone.utc)
        seed = ts.load_seed()
        after = datetime.now(timezone.utc)
        roots = ts.root_runs(seed)
        newest, oldest = started(roots[-1]), started(roots[0])
        self.assertTrue(before - timedelta(minutes=5) <= newest <= after - timedelta(minutes=5))
        self.assertLess(after - oldest, timedelta(hours=21))
        self.assertGreater(after - oldest, timedelta(hours=19))
        # every run moved by the same amount, and nothing lies in the future
        delta = newest - started(self.roots[-1])
        original = {r["id"]: r for r in self.runs}
        for run in seed["runs"]:
            self.assertEqual(started(run) - started(original[run["id"]]), delta)
            self.assertEqual(datetime.fromisoformat(run["end_time"]) - datetime.fromisoformat(original[run["id"]]["end_time"]), delta)
            self.assertLess(datetime.fromisoformat(run["end_time"]), after)
            self.assertTrue(all(DOTTED_SEGMENT.match(s) for s in run["dotted_order"].split(".")))
            self.assertEqual(run["dotted_order"].split(".")[-1][:22], started(run).strftime("%Y%m%dT%H%M%S%fZ"))
        self.assertAlmostEqual(seed["meta"]["clock"]["shifted_by_seconds"], delta.total_seconds(), places=3)
        for row in seed["feedback"]:
            self.assertLess(datetime.fromisoformat(row["created_at"]), after)
        # the committed seed in memory is untouched
        self.assertEqual(self.seed["meta"]["clock"]["shifted_by_seconds"], 0.0)

    def test_shift_to_now_accepts_a_fixed_now(self):
        now = datetime(2027, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        shifted = ts.shift_to_now(self.seed, now=now)
        self.assertEqual(started(ts.root_runs(shifted)[-1]), now - timedelta(minutes=5))
        self.assertEqual(ts.answer_key(shifted), self.answers)

    def test_remap_ids_gives_new_version_7_ids_and_root_id_equals_trace_id(self):
        remapped = ts.remap_ids(ts.load_seed(), thread_suffix="-u1")
        old_ids = {r["id"] for r in self.runs}
        new_ids = {r["id"] for r in remapped["runs"]}
        self.assertEqual(len(new_ids), len(self.runs))
        self.assertFalse(old_ids & new_ids)
        by_id = {r["id"]: r for r in remapped["runs"]}
        for run in remapped["runs"]:
            self.assertEqual(uuid.UUID(run["id"]).version, 7)
            if run["parent_run_id"] is None:
                self.assertEqual(run["id"], run["trace_id"])
            else:
                self.assertEqual(by_id[run["parent_run_id"]]["trace_id"], run["trace_id"])
            self.assertTrue(run["extra"]["metadata"]["thread_id"].endswith("-u1"))
            segments = run["dotted_order"].split(".")
            self.assertTrue(all(DOTTED_SEGMENT.match(s) for s in segments))
            self.assertTrue(segments[-1].endswith(run["id"]))
            # the id carries the run's own start time, so id order and time order agree
            self.assertEqual(uuid.UUID(run["id"]).int >> 80, (started(run) - EPOCH) // timedelta(milliseconds=1))
        for row in remapped["feedback"]:
            self.assertEqual(by_id[row["run_id"]]["trace_id"], row["trace_id"])
            self.assertTrue(row["thread_id"].endswith("-u1"))
        self.assertEqual(ts.answer_key(remapped), self.answers)  # trace keys, not run ids, carry the answers
        self.assertFalse(self.runs[0]["extra"]["metadata"]["thread_id"].endswith("-u1"))  # the source seed is untouched

    def test_remap_ids_uses_the_id_factory_it_is_given(self):
        calls = []

        def factory(start: datetime) -> uuid.UUID:
            calls.append(start)
            return uuid.UUID(ts.uuid7_at(start))

        remapped = ts.remap_ids(self.seed, new_id=factory)
        self.assertEqual(len(calls), len(self.runs))
        self.assertEqual(sorted(calls), sorted(started(r) for r in self.runs))
        self.assertTrue(all(isinstance(r["id"], str) for r in remapped["runs"]))

    # --- sampling, follow-up sets, printing ----------------------------------------------------

    def test_fixed_25_percent_sample_scores_65_and_catches_3(self):
        wrong = set(self.answers["s1_evaluator"]["flagged_trace_keys"])
        sample = ts.sample_runs(self.roots, ts.SAMPLING_RATE, ts.SAMPLING_SEED)
        self.assertEqual((ts.SAMPLING_RATE, len(sample), sum(self.key(r) in wrong for r in sample)), (0.25, 65, 3))
        self.assertEqual([self.key(r) for r in sample], [self.key(r) for r in ts.sample_runs(self.roots, 0.25, ts.SAMPLING_SEED)])
        moved = ts.root_runs(ts.remap_ids(ts.load_seed()))
        self.assertEqual({self.key(r) for r in ts.sample_runs(moved, 0.25, ts.SAMPLING_SEED)}, {self.key(r) for r in sample})
        self.assertNotEqual({self.key(r) for r in ts.sample_runs(self.roots, 0.25, ts.SAMPLING_SEED + 1)}, {self.key(r) for r in sample})
        self.assertEqual(self.answers["s1_filter_sample"], {"all_root_runs": {"scored": 260, "caught": 11}, "app_version_1_5_0": {"scored": 104, "caught": 11},
                                                            "sample_25_percent": {"scored": 65, "caught": 3}})
        self.assertEqual(self.seed["meta"]["sampling"], {"rate": 0.25, "seed": ts.SAMPLING_SEED})

    def test_follow_up_sets_flag_4_before_the_fix_and_0_after(self):
        follow = ts.load_followups()

        def flagged(runs):
            roots = [r for r in runs if r["parent_run_id"] is None]
            return len(roots), sum(bool(re.search(r"\b(opened|used)\b", question(r), re.I)) and "30 days" in reply(r) for r in roots)

        self.assertEqual(flagged(follow["before_fix"]["runs"]), (10, 4))
        self.assertEqual(flagged(follow["after_fix"]["runs"]), (10, 0))
        self.assertEqual((follow["before_fix"]["app_version"], follow["after_fix"]["app_version"]), ("1.5.0", "1.5.1"))
        self.assertEqual([question(r) for r in ts.root_runs(follow["before_fix"]["runs"])], [question(r) for r in ts.root_runs(follow["after_fix"]["runs"])])
        seed_keys = set(self.by_trace)
        for part in (follow["before_fix"], follow["after_fix"]):
            for run in part["runs"]:
                self.assertNotIn(run["extra"]["metadata"]["seed_trace_key"], seed_keys)
                self.assertEqual(run["tags"], ["followup:m7"])
                self.assertTrue(all(DOTTED_SEGMENT.match(s) for s in run["dotted_order"].split(".")))
        # moved with the seed, the follow-up traces lie between the newest seeded trace and now
        seed = ts.load_seed()
        moved = ts.load_followups(seed)
        newest = started(ts.root_runs(seed)[-1])
        for part in (moved["before_fix"], moved["after_fix"]):
            for run in part["runs"]:
                self.assertGreater(started(run), newest)
                self.assertLess(datetime.fromisoformat(run["end_time"]), datetime.now(timezone.utc))

    def test_describe_and_print_trace(self):
        out = io.StringIO()
        with redirect_stdout(out):
            summary = ts.describe(self.seed)
            ts.print_trace(self.seed, "t-0042")
            ts.print_trace(self.seed, self.by_trace["t-0042"][3]["id"])  # any run id of the trace works too
            ts.print_trace(self.seed, next(self.key(r) for r in self.roots if r["error"]))
            ts.print_trace(self.seed, "t-9999")
        text = out.getvalue()
        self.assertEqual(summary["conversations"], 200)
        self.assertEqual(summary["traces"], 260)
        self.assertEqual(summary["hours"], 20)
        self.assertEqual(summary["root_runs_by_version"], {"1.4.0": 156, "1.5.0": 104})
        self.assertIn("200 conversations, 260 traces (root runs)", text)
        self.assertIn("last 20 hours", text)
        self.assertEqual(text.count("t-0042  thread-m7-"), 2)
        self.assertIn("get_order_status [tool]", text)
        self.assertIn("(14 runs)", text)
        self.assertIn("ERROR: ", text)
        self.assertIn("No trace 't-9999'", text)
        self.assertIn("Metadata keys on the root run: app_version, customer_id, customer_segment, environment, lc_agent_name, revision_id, seed_trace_key, synthetic, thread_id", text)

    def test_latency_in_the_labels_is_the_agent_time_of_the_conversation(self):
        for conv in self.conversations[:40]:
            total = sum((datetime.fromisoformat(self.by_trace[k][0]["end_time"]) - started(self.by_trace[k][0])).total_seconds() for k in conv["trace_keys"])
            self.assertAlmostEqual(conv["latency_s"], total, places=3)
        self.assertGreater(statistics.median(c["latency_s"] for c in self.conversations), 1.0)


if __name__ == "__main__":
    unittest.main()
