"""One checker for every Module 7 exercise.

The notebooks, the unit tests and the command line (`workshop_modules/module_7/exercises/check.py`,
which the Instruqt track's Check button runs) all call the same function:

    ok, message = check("s1_evaluator", perform_eval)      # a function the learner wrote
    ok, message = check("s1_routing", selected_runs)        # or an answer computed in a notebook cell

`check` never raises. `ok` is True or False, and `message` is one line: on success it starts with
"✅ Verified: ", on failure it says what is wrong without giving the answer away.

How an answer is graded
-----------------------
Every checker id of section 6.6 of `docs/2026-11-19-module-7-monitoring-governance-prd.md` has one
answer, written by the seed generator to `workshop_modules/module_7/data/answers.json`. The checker
brings what it is given into the answer's shape, then compares:

- with `answers.json` when that file is there, or
- with `answer_hashes.json` (SHA-256 of each answer and of each of its fields) when it is not.
  The Instruqt sandbox deletes `answers.json` and the `solutions/` folder, so this is the path
  the Check button takes.

Both paths give the same verdict. Messages that name a failing case come from the "public cases"
in this file: small hand-written inputs with their expected output (`EVALUATOR_CASES`,
`REPORT_CASES`, `TRIAGE_CASES`, `ASSERTION_CANDIDATES`). They are deliberately not the graded
answers, so reading this file does not hand a learner the answer key.

What each id accepts
--------------------
A dictionary with the fields of the answer (see `ANSWER_FIELDS`), or for the five exercises that
are functions, the function itself:

    setup          the state file written by `scripts/module7_connect_langsmith.py` (path, dict or None)
    s1_evaluator   `perform_eval(run, example=None)`; or the flagged trace keys, runs or `apply_evaluator` rows
    s2_report      `summarise(report)`
    s2_claim       `flagged_in_subcategory(name, seed, labels, perform_eval)`
    s3_triage      `next_action(issue)`; or the list of three action codes
    s4_masking     `build_anonymizer()`

Nothing here calls a model, LangSmith or the network. The `s4_masking` check traces a model-free
agent into the local recorder of `utils/offline_capture.py` and refuses every non-local connection
while it runs. That check imports LangChain; no other check does.

Checking a file (`check_file`, the command line)
------------------------------------------------
- The exercise file is loaded with `load_exercise_function`. Its imports, assignments, definitions
  and blocks (`if`, `for`, `try`, `with`) run; a bare top-level call (a `print`, a test call), an
  `assert` and a `raise` do not. When a check fails and such a line was skipped, the message says
  which line, because a function that depends on it fails here and passes when imported.
- `s1_evaluator` has one more step. LangSmith runs the source of a code evaluator on its own, so
  after the function passes inside its file, its `def` is compiled alone and checked again. A
  function that needs an import, a constant or a helper from the rest of the file fails with a
  message that names what is missing. So does a function whose body imports something that is
  not in Python's standard library (this repository's `utils` or `evaluators`, an installed
  package): the import works here and fails in LangSmith. The imports are read from the source
  with `ast`; this is a check of what is written, not a sandbox.
- Before a function exercise is graded, the generated data files of the module are compared with
  a fresh generation (`changed_data_files`). A missing or edited seed, label, report or board file
  would otherwise be blamed on the learner's function, or pass a wrong one. The message names the
  file and the command that restores it: `check.py --restore-data` (`restore_data_files`), which
  never writes `answers.json` where it is absent.
- Code that calls `sys.exit()` is reported as a failed check. The command line prints exactly one
  `PASS:` or `FAIL:` line per id and exits with 0 only when every line is a `PASS:`.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable

from utils import trace_seeding as ts

REPO_ROOT = ts.REPO_ROOT
ANSWERS_PATH = ts.DATA / ts.ANSWERS_FILE
HASHES_PATH = ts.DATA / ts.HASHES_FILE
EXERCISES_DIR = REPO_ROOT / "workshop_modules" / "module_7" / "exercises"
STATE_FILE = REPO_ROOT / ".m7_state.json"  # written by scripts/module7_connect_langsmith.py
_DATA_REL = "workshop_modules/module_7/data"  # the data folder as messages name it, relative to the repository root
_SEED_REL = f"{_DATA_REL}/{ts.SEED_FILE}"

VERIFIED = "✅ Verified: "
FEEDBACK_KEY = "wrong_return_window"

# The five exercises that are functions in a file: checker id -> (file name, function name, how to define it).
EXERCISE_FILES: dict[str, tuple[str, str, str]] = {
    "s1_evaluator": ("return_window_evaluator.py", "perform_eval", "perform_eval(run, example=None)"),
    "s2_report": ("read_the_report.py", "summarise", "summarise(report)"),
    "s2_claim": ("read_the_report.py", "flagged_in_subcategory", "flagged_in_subcategory(name, seed, labels, perform_eval)"),
    "s3_triage": ("triage.py", "next_action", "next_action(issue)"),
    "s4_masking": ("masking.py", "build_anonymizer", "build_anonymizer()"),
}
# Ids that `exercises/check.py` can run: the five above and the setup check, which reads a state file.
COMMAND_LINE_IDS = ("setup", *EXERCISE_FILES)


# ---------------------------------------------------------------------------------------------
# The shape of every answer (PRD section 6.6, `answers.json`)
# ---------------------------------------------------------------------------------------------

_INT, _STR, _BOOL = "a whole number", "text", "True or False"
_RATE, _SHARE = "a fraction between 0 and 1 (3 decimal places)", "a fraction between 0 and 1 (2 decimal places)"
_STRS, _SORTED_STRS, _SORTED_INTS = "a list of text values, in order", "a list of text values", "a list of whole numbers"
_SCORED_CAUGHT = {"scored": _INT, "caught": _INT}
_BLOCK = {"policy_type": _STR, "exception": _STR}

ANSWER_FIELDS: dict[str, dict[str, Any]] = {
    "s1_signals": {"errored_root_runs": _INT, "thumbs_down_conversations": _INT, "thumbs_down_after_order_not_found": _INT,
                   "thumbs_down_on_wrong_return_window": _INT},
    "s1_evaluator": {"flagged_trace_keys": _SORTED_STRS},
    "s1_filter_sample": {"all_root_runs": _SCORED_CAUGHT, "app_version_1_5_0": _SCORED_CAUGHT, "sample_25_percent": _SCORED_CAUGHT},
    "s1_alert": {"background_max_in_5_minutes": _INT, "burst_errors": _INT, "threshold": _INT, "failing_tool": _STR},
    "s1_routing": {"selected": _INT},
    "s2_report": {"largest_category": _STR, "largest_category_conversations": _INT, "largest_category_share": _SHARE,
                  "highest_error_rate_subcategory": _STR, "highest_error_rate": _RATE},
    "s2_claim": {"conversations": _INT, "error_rate": _RATE, "flagged": _INT},
    "s3_evidence": {"missing_tool": _STR, "under_run": _STR},
    "s3_triage": {"actions": _STRS},
    "s3_assertions": {"assertions": _SORTED_STRS},
    "s4_leak": {"root_runs_with_raw_email": _INT, "in_inputs": _INT, "in_outputs": _INT},
    "s4_masking": {"middleware_only_more_than_zero": _BOOL, "with_anonymizer": _INT, "control_string_unchanged": _BOOL},
    "s4_routes": {"base_url": _STR},
    "s4_blocks": {"402": _BLOCK, "429": _BLOCK, "403": _BLOCK, "retried_statuses": _SORTED_INTS},
}
EXERCISE_IDS = ("setup", *ANSWER_FIELDS)

# An id with a single field also accepts the bare value: check("s1_routing", 11), check("s3_triage", [...]).
_SINGLE_FIELD = {exercise_id: next(iter(fields)) for exercise_id, fields in ANSWER_FIELDS.items() if len(fields) == 1}


class _Problem(Exception):
    """A failure with a message for the learner. Raised inside this module, turned into `(False, message)` by `check`."""


def _round(value: float, places: int) -> float:
    return float(Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _coerce(kind, value, name: str):
    """Bring one field into the canonical type of the answer key, or raise `_Problem` naming the field."""
    if isinstance(kind, dict):
        if not isinstance(value, dict):
            raise _Problem(f"`{name}` should be a dictionary with the keys {', '.join(kind)}; got {type(value).__name__}.")
        value = {str(key): item for key, item in value.items()}
        missing = [key for key in kind if key not in value]
        if missing:
            raise _Problem(f"`{name}` is missing {', '.join(missing)}.")
        return {key: _coerce(kind[key], value[key], f"{name}.{key}") for key in kind}
    number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == _INT:
        if number and float(value) == int(value):
            return int(value)
    elif kind == _STR:
        if isinstance(value, str):
            return value.strip()
    elif kind == _BOOL:
        if isinstance(value, bool):
            return value
    elif kind in (_RATE, _SHARE):
        if number:
            if not 0 <= value <= 1:
                raise _Problem(f"`{name}` should be a fraction between 0 and 1 (0.25 for 25%), not a percentage; got {value}.")
            return _round(value, 3 if kind == _RATE else 2)
    elif kind in (_STRS, _SORTED_STRS):
        if isinstance(value, (list, tuple, set, frozenset)) and all(isinstance(item, str) for item in value):
            return sorted(value) if kind == _SORTED_STRS or isinstance(value, (set, frozenset)) else list(value)
    elif kind == _SORTED_INTS:
        if isinstance(value, (list, tuple, set, frozenset)) and all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return sorted(value)
    raise _Problem(f"`{name}` should be {kind}; got {value!r}.")


def _normalise(exercise_id: str, value) -> dict:
    """The answer for `exercise_id` in canonical form: the fields of `ANSWER_FIELDS`, each in its canonical type."""
    fields = ANSWER_FIELDS[exercise_id]
    if not isinstance(value, dict):
        raise _Problem(f"give a dictionary with the keys {', '.join(fields)}; got {type(value).__name__}.")
    value = {str(key): item for key, item in value.items()}
    missing = [key for key in fields if key not in value]
    if missing:
        raise _Problem(f"the answer is missing {', '.join(missing)}. Expected keys: {', '.join(fields)}.")
    return {key: _coerce(kind, value[key], key) for key, kind in fields.items()}


# ---------------------------------------------------------------------------------------------
# Grading: answers.json when it is there, otherwise the hashes
# ---------------------------------------------------------------------------------------------


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def grading_source() -> str:
    """Which file the checker compares with right now: "answers", "hashes" or "none"."""
    if isinstance(_read_json(ANSWERS_PATH), dict):
        return "answers"
    return "hashes" if isinstance(_read_json(HASHES_PATH), dict) else "none"


def _wrong_fields(exercise_id: str, value: dict) -> list[str]:
    """The fields of a normalised answer that differ from the answer key (an empty list means it is right)."""
    answers = _read_json(ANSWERS_PATH)
    if isinstance(answers, dict) and exercise_id in answers:
        expected = _normalise(exercise_id, answers[exercise_id])
        return [field for field in value if ts.canonical_json(value[field]) != ts.canonical_json(expected[field])]
    hashes = _read_json(HASHES_PATH)
    field_hashes = ((hashes or {}).get("fields") or {}).get(exercise_id)
    if not isinstance(field_hashes, dict):
        raise _Problem(
            f"the checker cannot grade {exercise_id}: neither {ts.ANSWERS_FILE} nor {ts.HASHES_FILE} in "
            f"workshop_modules/module_7/data has an entry for it. Restore the one file {_DATA_REL}/{ts.HASHES_FILE} "
            f"(in a git checkout: `git checkout -- {_DATA_REL}/{ts.HASHES_FILE}`; in the hands-on track: tell your instructor) and try again."
        )
    wrong = [field for field in value if ts.sha256_of(value[field]) != field_hashes.get(field)]
    if not wrong and ts.sha256_of(value) != hashes["answers"].get(exercise_id):
        wrong = list(value)  # every field matches but the whole does not: the hash file itself is inconsistent
    return wrong


def _show(value) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "..."


# ---------------------------------------------------------------------------------------------
# Public cases: small hand-written inputs, used only to say WHICH case fails
# ---------------------------------------------------------------------------------------------


def _turn(question: str, reply: str | None, error: str | None = None) -> dict:
    """A root run in the shape of the seed: the question in the inputs, the conversation in the outputs."""
    outputs: dict = {} if reply is None else {
        "messages": [{"type": "human", "content": question}, {"type": "ai", "name": "deep_support_agent", "content": reply, "tool_calls": []}],
        "files": {},
    }
    return {"name": "deep_support_agent", "run_type": "chain", "parent_run_id": None,
            "inputs": {"messages": [{"role": "user", "content": question}]}, "outputs": outputs, "error": error}


# (what the case is, the run, the expected score, the message when the evaluator gets it wrong)
EVALUATOR_CASES: list[tuple[str, dict, bool, str]] = [
    (
        "a customer who opened the product and is told 30 days",
        _turn("I opened my wireless mouse from order ORD-2025-0050 last week. How long do I have to return it?",
              "You have 30 days from delivery to return your wireless mouse."),
        True,
        "it misses a wrong answer: the customer says the product was opened and the reply gives 30 days.",
    ),
    (
        "a customer who used the product and is told 30 days",
        _turn("I've already used the keyboard I bought a few times. What is the return window?",
              "No problem: TechHub accepts returns within 30 days from delivery, so your keyboard is still eligible."),
        True,
        "it misses a wrong answer: the customer says the product was used and the reply gives 30 days.",
    ),
    (
        "a correct answer about an unopened item",
        _turn("My monitor is still unopened. How long do I have to return it?",
              "Per our Return Policy, unopened electronics can be returned within 30 days from delivery. Your monitor qualifies."),
        False,
        "it also flags a correct answer about an unopened item (30 days is right for an unopened product; 'unopened' is not 'opened').",
    ),
    (
        "a correct answer about an unused, sealed item",
        _turn("I never took the headset out of its box; it is unused and sealed. How many days do I have to return it?",
              "Since your headset is unopened, our Return Policy gives you 30 days from delivery to return it."),
        False,
        "it also flags a correct answer about an unused, sealed item (match whole words: 'unused' is not 'used').",
    ),
    (
        "a correct answer that gives an opened item 14 days",
        _turn("The box of my laptop has been opened. By when do I need to send it back?",
              "Because your laptop has been opened, our Return Policy gives you 14 days from delivery to return it."),
        False,
        "it also flags a correct answer: the customer opened the product and the reply gives 14 days, which is the policy.",
    ),
    (
        "a run that failed (error set, outputs empty)",
        _turn("I opened my tablet yesterday. Can I still return it?", None, error="TimeoutError: a tool call timed out"),
        False,
        "it flags a run that failed. A failed run has no reply, so there is nothing to flag.",
    ),
    (
        "a question that is not about returns",
        _turn("Has order ORD-2025-0050 shipped yet?", "Your order ORD-2025-0050 shipped on Monday and should arrive within 3 days."),
        False,
        "it flags a turn that is not about a return window at all.",
    ),
]


def _cluster(cluster_id: str, parent: str | None, name: str, conversations: int, error_rate: float) -> dict:
    return {"id": cluster_id, "parent_id": parent, "parent_name": None, "level": 1 if parent is None else 0, "name": name,
            "description": "", "num_runs": conversations, "stats": {"error_rate": error_rate, "latency_p50": 1.0, "cost_p50": 0.01}}


# (what the case is, a small report, the expected result of summarise(report))
REPORT_CASES: list[tuple[str, dict, dict]] = [
    (
        "a small test report with two categories (Billing 6 conversations, Shipping 4)",
        {"clusters": [
            _cluster("a", None, "Billing", 6, 0.167),
            _cluster("b", None, "Shipping", 4, 0.25),
            _cluster("a1", "a", "Invoice copies", 5, 0.0),
            _cluster("a2", "a", "Double charges", 1, 1.0),
            _cluster("b1", "b", "Late parcels", 4, 0.25),
        ]},
        {"largest_category": "Billing", "largest_category_conversations": 6, "largest_category_share": 0.6,
         "highest_error_rate_subcategory": "Double charges", "highest_error_rate": 1.0},
    ),
    (
        "a small test report in which the category Returns has a single subcategory, Return labels",
        {"clusters": [
            _cluster("r", None, "Returns", 3, 0.667),
            _cluster("c", None, "Accounts", 7, 0.143),
            _cluster("r1", "r", "Return labels", 3, 0.667),
            _cluster("c1", "c", "Password resets", 4, 0.25),
            _cluster("c2", "c", "Address changes", 3, 0.0),
        ]},
        {"largest_category": "Accounts", "largest_category_conversations": 7, "largest_category_share": 0.7,
         "highest_error_rate_subcategory": "Return labels", "highest_error_rate": 0.667},
    ),
]

# Two extra issues for next_action, beside the three on the board: (what the case is, the issue, expected action, why).
TRIAGE_CASES: list[tuple[str, dict, str, str]] = [
    (
        "an actionable issue in status 'fixing' with one pull request, severity high",
        {"id": "extra-1", "type": "actionable", "name": "Agent promises a delivery date the order service never gave", "severity": 1,
         "status": "fixing", "tags": ["Hallucination"], "proposed_fix": "Quote only dates that a tool returned.",
         "fixes": [{"id": "extra-fix-1", "branch": "engine/quote-tool-dates-only", "pr_number": 57, "provider": "github"}],
         "recurrences_since_watching": 0},
        "review_pull_request",
        "a fix is already in flight (status 'fixing', one entry in `fixes`), whatever the severity",
    ),
    (
        "a finding (type 'finding') that is still in status 'open', severity high",
        {"id": "extra-2", "type": "finding", "name": "Latency of product searches rose after the last release", "severity": 1,
         "status": "open", "tags": ["Inefficient path"], "fixes": [], "recurrences_since_watching": 0},
        "save_for_later",
        "a finding is an observation with nothing to fix yet, whatever its status or severity",
    ),
]

# Six candidate assertions for the offline example of Engine issue 1 (Section 3). An assertion is a short
# claim about a correct answer. `holds` is a wording check that stands in for a judge: a calculation on two
# fixed texts, not the product's Assertions evaluator. Two separate the recorded (wrong) answer from the
# corrected one, two hold for both, two fail for both.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}\b")
ASSERTION_CANDIDATES: list[dict] = [
    {"key": "gives_a_window_in_days", "comment": "Tells the customer how many days they have to return the product",
     "holds": lambda text: bool(re.search(r"\b\d+[ -]days?\b", text))},
    {"key": "states_14_day_window", "comment": "States that opened electronics can be returned within 14 days of delivery",
     "holds": lambda text: bool(re.search(r"\b14[ -]days?\b", text))},
    {"key": "gives_the_last_return_date", "comment": "Gives the calendar date of the last day on which the product can be returned",
     "holds": lambda text: bool(_DATE.search(text))},
    {"key": "no_30_day_claim", "comment": "Does not tell the customer that an opened product has a 30-day return window",
     "holds": lambda text: not re.search(r"\b30[ -]days?\b", text)},
    {"key": "counts_from_delivery", "comment": "Counts the return window from the delivery date",
     "holds": lambda text: "from delivery" in text.lower()},
    {"key": "explains_the_refund_method", "comment": "Says that the refund goes to the original payment method",
     "holds": lambda text: "original payment method" in text.lower()},
]

# The answer a corrected agent gives to the question of the evidence trace. Its wording follows the
# generator's template for a correct opened-item answer and data/documents/policies/return_policy.md.
CORRECTED_ANSWER = (
    "Because the product has been opened, our Return Policy gives you 14 days from delivery to return it. "
    "It needs to be in good working condition with all accessories included."
)


def assertion_case(seed: dict | None = None, board: dict | None = None) -> dict:
    """The question, the recorded (wrong) answer and the corrected answer that the six candidate assertions are tried on.

    The trace is the one the sample Engine board proposes as an offline example for issue 1. Returns
    `{"trace_key", "question", "recorded_answer", "corrected_answer"}`. A calculation on seed data,
    not the product.
    """
    seed = seed or ts.load_seed(shift_to_now=False)
    board = board or ts.load_engine_issues()
    key = board["offline_examples"][board["issues"][0]["id"]][0]["seed_trace_key"]
    root = ts.trace_runs(seed, key)[0]
    return {"trace_key": key, "question": ts.question_text(root), "recorded_answer": ts.reply_text(root), "corrected_answer": CORRECTED_ANSWER}


def assertion_table(case: dict | None = None) -> list[dict]:
    """One row per candidate assertion: does it hold for the recorded answer, and for the corrected one?

    Rows are `{"key", "comment", "holds_for_recorded", "holds_for_corrected", "separates"}`; `separates`
    is True when the assertion holds for the corrected answer and fails for the recorded one, which is
    what makes it worth adding to the test case. A calculation on two texts, not the product.
    """
    case = case or assertion_case()
    rows = []
    for candidate in ASSERTION_CANDIDATES:
        recorded, corrected = candidate["holds"](case["recorded_answer"]), candidate["holds"](case["corrected_answer"])
        rows.append({"key": candidate["key"], "comment": candidate["comment"], "holds_for_recorded": recorded,
                     "holds_for_corrected": corrected, "separates": corrected and not recorded})
    return rows


# ---------------------------------------------------------------------------------------------
# The text of a passed check
# ---------------------------------------------------------------------------------------------


def _percent(fraction: float) -> str:
    return f"{100 * fraction:.1f}".rstrip("0").rstrip(".") + "%"


def _list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


_BLOCK_TEXT = {"spend_limit": "spend limit", "rate_limit": "rate limit", "model_access": "model access"}

_PASS_TEXT: dict[str, Callable[[dict], str]] = {
    "s1_signals": lambda v: (
        f"{v['errored_root_runs']} root runs errored; {v['thumbs_down_conversations']} conversations got a thumbs-down, "
        f"{v['thumbs_down_after_order_not_found']} of them after an 'Order ... not found.' tool result; the wrong "
        f"return-window answers got {v['thumbs_down_on_wrong_return_window']}."
    ),
    "s1_evaluator": lambda v: f"exactly the {len(v['flagged_trace_keys'])} planted traces are flagged.",
    "s1_filter_sample": lambda v: (
        f"all root runs: {v['all_root_runs']['scored']} scored, {v['all_root_runs']['caught']} caught; "
        f"app_version 1.5.0 only: {v['app_version_1_5_0']['scored']} scored, {v['app_version_1_5_0']['caught']} caught; "
        f"25% sample: {v['sample_25_percent']['scored']} scored, {v['sample_25_percent']['caught']} caught."
    ),
    "s1_alert": lambda v: (
        f"background errors reach at most {v['background_max_in_5_minutes']} in any 5 minutes and the burst has {v['burst_errors']}, "
        f"so {v['threshold']} is the smallest threshold the background cannot reach; the failing tool is {v['failing_tool']}."
    ),
    "s1_routing": lambda v: f"the routing filter selects {v['selected']} root runs.",
    "s2_report": lambda v: (
        f"largest category: {v['largest_category']} ({v['largest_category_conversations']} conversations, "
        f"{_percent(v['largest_category_share'])}); highest error rate: {v['highest_error_rate_subcategory']} ({_percent(v['highest_error_rate'])})."
    ),
    "s2_claim": lambda v: (
        f"the subcategory has {v['conversations']} conversations and an error rate of {_percent(v['error_rate'])}, "
        f"and the evaluator flags {v['flagged']} of them."
    ),
    "s3_evidence": lambda v: f"the evidence trace has no {v['missing_tool']} call under {v['under_run']}.",
    "s3_triage": lambda v: "; ".join(f"issue {i} {action}" for i, action in enumerate(v["actions"], start=1)) + ".",
    "s3_assertions": lambda v: f"{_list(v['assertions'])} hold for the corrected answer and fail for the recorded one.",
    "s4_leak": lambda v: (
        f"{v['root_runs_with_raw_email']} root run contains a raw email address: {v['in_inputs']} in inputs, {v['in_outputs']} in outputs."
    ),
    "s4_masking": lambda v: (
        "with the middleware alone the email is still in uploaded payloads; with the anonymizer "
        f"{v['with_anonymizer']} payloads contain it, and the control string is uploaded unchanged."
    ),
    "s4_routes": lambda v: f"calls go to {v['base_url']}.",
    "s4_blocks": lambda v: (
        "; ".join(f"{status} is a {_BLOCK_TEXT.get(v[status]['policy_type'], v[status]['policy_type'])} block ({v[status]['exception']})"
                  for status in ("402", "429", "403"))
        + f"; the agent retries only {_list([str(status) for status in v['retried_statuses']])}."
    ),
}


def expected_line(exercise_id: str, answers: dict | None = None) -> str:
    """The line a passed check prints for `exercise_id`, built from the answer key (`answers.json` by default).

    `check` builds its success message with the same function from the value it has just verified,
    so a notebook run that prints `message` contains this line. For checks that ran a learner's
    function the message may continue after it with what was measured. Needs `answers.json`; the
    `setup` check has no line here because it depends on the state file.
    """
    answers = answers if answers is not None else json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
    return VERIFIED + _PASS_TEXT[exercise_id](_normalise(exercise_id, answers[exercise_id]))


def _grade(exercise_id: str, value: dict, detail: str = "") -> tuple[bool, str]:
    """Normalise `value`, compare it with the answer key and build the message."""
    value = _normalise(exercise_id, value)
    wrong = _wrong_fields(exercise_id, value)
    if wrong:
        given = ", ".join(f"{field} = {_show(value[field])}" for field in wrong)
        return False, f"not right yet: {_list([f'`{field}`' for field in wrong])}. You gave {given}."
    return True, VERIFIED + _PASS_TEXT[exercise_id](value) + (f" {detail}" if detail else "")


# ---------------------------------------------------------------------------------------------
# Calling a learner's function
# ---------------------------------------------------------------------------------------------


def _name(function) -> str:
    return getattr(function, "__name__", "the function")


def _not_implemented(function, definition: str) -> _Problem:
    file_name = next((file for file, name, _ in EXERCISE_FILES.values() if name == _name(function)), "the exercise file")
    return _Problem(f"{_name(function)} is not implemented yet: it still raises NotImplementedError. Write the body of {definition} in {file_name}, then run this check again.")


_EXIT_ADVICE = "A function under check returns its result: remove the call to sys.exit() (or the `raise SystemExit`)."


def _call(function, *args, on: str, definition: str):
    """Call a learner's function. NotImplementedError, `sys.exit()` and every other exception become a `_Problem` that names the case."""
    try:
        return function(*args)
    except NotImplementedError:
        raise _not_implemented(function, definition) from None
    except SystemExit:  # not an `Exception`: uncaught, it would end the check with exit code 0 and no result line
        raise _Problem(f"{_name(function)} called sys.exit() (it raised SystemExit) on {on}. {_EXIT_ADVICE}") from None
    except Exception as exc:  # noqa: BLE001 - whatever the learner's code raises is reported, not propagated
        raise _Problem(f"{_name(function)} raised {_describe(exc)} on {on}.") from None


def _describe(exc: BaseException) -> str:
    """An exception as `Type: first line of its message`, short enough for a one-line check message."""
    detail = str(exc).splitlines()[0][:120] if str(exc) else ""
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


def _accepts(function, *args) -> bool:
    try:
        inspect.signature(function).bind(*args)
    except TypeError:
        return False
    except ValueError:  # no signature available (a builtin): let the call decide
        return True
    return True


# ---------------------------------------------------------------------------------------------
# The generated data files: are they intact, and how to get them back
# ---------------------------------------------------------------------------------------------

RESTORE_COMMAND = "uv run python workshop_modules/module_7/exercises/check.py --restore-data"


def _same_json(path: Path, generated: bytes) -> bool:
    """Whether the file holds the same JSON document as `generated`. Line endings and spacing do not count."""
    try:
        return json.loads(path.read_bytes().decode("utf-8-sig")) == json.loads(generated.decode("utf-8"))
    except (OSError, ValueError):
        return False


def changed_data_files() -> list[str]:
    """The generated files of `workshop_modules/module_7/data/` that are missing or differ from a fresh generation.

    The seven files of `utils.trace_seeding.DATA_FILES` are generated from code, so a fresh
    generation (a fraction of a second) says what each must contain. `answers.json` is compared
    only when it is there: the hands-on track removes it on purpose. Raises whatever the generator
    raises (it reads the TechHub database and documents).
    """
    changed = []
    for name, generated in ts.seed_files().items():
        path = ts.DATA / name
        if not path.exists():
            if name != ts.ANSWERS_FILE:
                changed.append(name)
        elif not _same_json(path, generated):
            changed.append(name)
    return changed


def restore_data_files() -> list[str]:
    """Write a fresh generation over every generated data file that is missing or differs. Returns the names written.

    `answers.json` is rewritten only where it already exists, so this never puts the answer key
    back into a folder that was set up without it (the hands-on track). Exercise files are not
    touched. This is what `check.py --restore-data` runs.

    A restore is exact: a file is rewritten when its bytes differ, also when it still holds the
    same JSON document (`changed_data_files` would not report it). The `setup` check compares the
    seed file byte for byte, so a restore has to leave the bytes of a fresh generation.
    """
    written = []
    for name, generated in ts.seed_files().items():
        path = ts.DATA / name
        if path.exists() and path.read_bytes() == generated:
            continue
        if name == ts.ANSWERS_FILE and not path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(generated)
        written.append(name)
    return written


def _data_problem() -> str | None:
    """A message when a generated data file is missing or was changed, else `None`. Never raises."""
    try:
        names = changed_data_files()
    except Exception:  # noqa: BLE001 - the generator could not run; the check itself then says what it cannot read
        return None
    if not names:
        return None
    files = _list([f"{_DATA_REL}/{name}" for name in names])
    return (
        f"the data {'file' if len(names) == 1 else 'files'} {files} {'is' if len(names) == 1 else 'are'} missing or "
        f"{'was' if len(names) == 1 else 'were'} changed, so this check cannot grade your work. This is not about your function. "
        f"Run `{RESTORE_COMMAND}` in the terminal: it regenerates the data files and leaves your exercise files alone. Then check again."
    )


# ---------------------------------------------------------------------------------------------
# setup: the state file of scripts/module7_connect_langsmith.py
# ---------------------------------------------------------------------------------------------

_CONNECT_COMMAND = "uv run python scripts/module7_connect_langsmith.py"
# How to get the seed file back. One wording, also used by `scripts/module7_connect_langsmith.py`.
# The command regenerates the file from code, so it works where there is no git history (the
# sandbox of the hands-on track) and in every challenge of that track, and it never writes the
# answer key back where the track removed it. `git checkout` is named for the one file only:
# restoring the whole data folder from git would bring the answer key back.
RESTORE_SEED = (
    f"Restore it: run `{RESTORE_COMMAND}`, which regenerates the data files (in a git checkout, "
    f"`git checkout -- {_SEED_REL}` restores that one file as well; in the hands-on track, Skip on the challenge you are in "
    f"runs the same command). Then run `{_CONNECT_COMMAND}` again (add `--skip` to continue without a key)."
)


def _check_setup(obj) -> tuple[bool, str]:
    """Setup is done when the state file says the seed verified and LangSmith is `verified` or `skipped`, and the seed file is intact.

    `obj` is the state as a dictionary, the path of the state file, or None for the default place:
    the environment variable `M7_STATE_FILE`, else `.m7_state.json` in the repository root. A key
    is never required: `skipped` passes. The seed file is compared, by SHA-256, with a fresh
    generation (`utils.trace_seeding.seed_files()`), which takes a fraction of a second.
    """
    if isinstance(obj, dict):
        state = obj
    else:
        if obj is not None and not isinstance(obj, (str, Path)):
            raise _Problem(f"give the state as a dictionary or as the path of the state file; got {type(obj).__name__}.")
        path = Path(obj or os.environ.get("M7_STATE_FILE") or STATE_FILE)
        if not path.exists():
            raise _Problem(
                f"setup has not run yet: there is no state file {path.name}. Run `{_CONNECT_COMMAND}` and paste your "
                f"LangSmith API key at the prompt, or run `{_CONNECT_COMMAND} --skip` to continue without a key."
            )
        state = _read_json(path)
        if not isinstance(state, dict):
            raise _Problem(f"the state file {path.name} is not valid JSON. Run `{_CONNECT_COMMAND}` again (add `--skip` to continue without a key).")
    if state.get("seed_verified") is not True:
        raise _Problem(
            f"the state file does not say that the seed verified (`seed_verified` is not true). Run `{_CONNECT_COMMAND}` "
            "again (add `--skip` to continue without a key): it compares the seed file with a fresh generation and says what to do if they differ."
        )
    langsmith = state.get("langsmith")
    if langsmith not in ("verified", "skipped"):
        raise _Problem(
            f"the state file says LangSmith is {langsmith!r}, expected 'verified' or 'skipped'. Run `{_CONNECT_COMMAND}` "
            "again: paste a working key, or add `--skip` to continue without one. A key is never required."
        )
    seed_path = ts.DATA / ts.SEED_FILE
    if not seed_path.exists():
        raise _Problem(f"the seed file {_SEED_REL} is missing. {RESTORE_SEED}")
    actual = hashlib.sha256(seed_path.read_bytes()).hexdigest()
    try:
        fresh = hashlib.sha256(ts.seed_files()[ts.SEED_FILE]).hexdigest()
    except Exception as exc:  # noqa: BLE001 - the generator needs the TechHub database and documents
        raise _Problem(
            f"the checker could not regenerate the seed to compare it ({type(exc).__name__}). Run `{_CONNECT_COMMAND} --skip` to see the "
            "error: it makes the same comparison and prints the traceback."
        ) from None
    recorded = state.get("seed_sha256")
    if actual != fresh or (recorded and recorded != actual):
        raise _Problem(
            f"the seed file {_SEED_REL} has changed: its SHA-256 no longer matches the generated seed. {RESTORE_SEED}"
        )
    key_note = "LangSmith is connected" if langsmith == "verified" else "you continue without a LangSmith key, which is fine"
    return True, VERIFIED + f"the seed is intact and verified, and {key_note}."


# ---------------------------------------------------------------------------------------------
# s1_evaluator
# ---------------------------------------------------------------------------------------------

_EVALUATOR_DEFINITION = EXERCISE_FILES["s1_evaluator"][2]


def _expected_flagged_count() -> int:
    """How many root runs the evaluator should flag: a design constant of the seed, safe to print (the lab states it)."""
    answers = _read_json(ANSWERS_PATH)
    if isinstance(answers, dict) and "s1_evaluator" in answers:
        return len(answers["s1_evaluator"]["flagged_trace_keys"])
    return ts.OPENED_BY_VERSION[ts.NEW_VERSION]


def _score(function, run: dict, on: str) -> bool:
    """Call a code evaluator on one run and return its wrong_return_window score as a bool."""
    result = _call(function, run, on=on, definition=_EVALUATOR_DEFINITION)
    if not isinstance(result, dict) or FEEDBACK_KEY not in result:
        raise _Problem(f'{_name(function)} must return {{"{FEEDBACK_KEY}": True}} or {{"{FEEDBACK_KEY}": False}}; it returned {_show_python(result)} on {on}.')
    score = result[FEEDBACK_KEY]
    if not isinstance(score, bool) and score not in (0, 1):
        raise _Problem(f'the value of "{FEEDBACK_KEY}" must be True or False; {_name(function)} returned {_show_python(score)} on {on}.')
    return bool(score)


def _show_python(value) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _check_evaluator_function(function) -> tuple[bool, str]:
    if not _accepts(function, {}, None) or not _accepts(function, {}):
        raise _Problem(
            f"define the function as {_EVALUATOR_DEFINITION}. LangSmith calls it with the run alone on live traffic and with "
            "a second argument when the evaluator is tested against a dataset example."
        )
    for what, run, expected, hint in EVALUATOR_CASES:
        if _score(function, copy.deepcopy(run), on=what) != expected:
            raise _Problem(f"{_name(function)} is not right yet: {hint}")
    failed = copy.deepcopy(EVALUATOR_CASES[0][1])
    failed.update(outputs=None, error="TimeoutError")
    if _score(function, failed, on="a run that failed (its outputs are None)"):
        raise _Problem(f"{_name(function)} flags a run that failed. A failed run has no reply, so there is nothing to flag.")

    roots = ts.root_runs(ts.load_seed(shift_to_now=False))
    flagged = sorted(ts.trace_key(run) for run in roots if _score(function, run, on=f"trace {ts.trace_key(run)} of the seed"))
    value = _normalise("s1_evaluator", {"flagged_trace_keys": flagged})
    if _wrong_fields("s1_evaluator", value):
        expected = _expected_flagged_count()
        tail = f"expected {expected}." if len(flagged) != expected else f"that is the right number, but they are not the {expected} wrong answers."
        raise _Problem(f"{_name(function)} flags {len(flagged)} of {len(roots)} root runs of the seed, {tail}")
    return True, VERIFIED + _PASS_TEXT["s1_evaluator"](value) + f" {_name(function)} flags {len(flagged)} of {len(roots)} root runs and passes {len(EVALUATOR_CASES) + 1} control cases."


def _as_trace_keys(obj) -> list[str]:
    """Trace keys from a list of keys, of runs, or of `apply_evaluator` rows (only the rows that are flagged)."""
    keys = set()
    for item in obj:
        if isinstance(item, str):
            keys.add(item)
        elif isinstance(item, dict) and "score" in item and "trace_key" in item:
            if item.get("key", FEEDBACK_KEY) == FEEDBACK_KEY and (item["score"] is True or (isinstance(item["score"], (int, float)) and item["score"] > 0.5)):
                keys.add(item["trace_key"])
        elif isinstance(item, dict):
            keys.add(ts.trace_key(item))
        else:
            raise _Problem(f"give the flagged traces as trace keys such as 't-0042', as runs, or as rows from apply_evaluator; got {type(item).__name__}.")
    return sorted(keys)


def _check_evaluator(obj) -> tuple[bool, str]:
    if callable(obj):
        return _check_evaluator_function(obj)
    if isinstance(obj, dict):
        return _grade("s1_evaluator", obj)
    try:
        keys = _as_trace_keys(obj)
    except (KeyError, TypeError):
        raise _Problem("give the evaluator function, or the flagged traces as trace keys, runs or rows from apply_evaluator.") from None
    value = _normalise("s1_evaluator", {"flagged_trace_keys": keys})
    if _wrong_fields("s1_evaluator", value):
        expected = _expected_flagged_count()
        tail = f"expected {expected}." if len(keys) != expected else f"that is the right number, but they are not the {expected} wrong answers."
        raise _Problem(f"{len(keys)} traces are flagged, {tail}")
    return True, VERIFIED + _PASS_TEXT["s1_evaluator"](value)


# ---------------------------------------------------------------------------------------------
# s2_report and s2_claim
# ---------------------------------------------------------------------------------------------

_REPORT_KEYS = tuple(ANSWER_FIELDS["s2_report"])
_SUMMARISE_DEFINITION = EXERCISE_FILES["s2_report"][2]
_CLAIM_DEFINITION = EXERCISE_FILES["s2_claim"][2]


def _summary(function, report: dict, on: str) -> dict:
    result = _call(function, copy.deepcopy(report), on=on, definition=_SUMMARISE_DEFINITION)
    if not isinstance(result, dict):
        raise _Problem(f"{_name(function)} must return a dictionary with the keys {', '.join(_REPORT_KEYS)}; it returned {type(result).__name__} on {on}.")
    try:
        return _normalise("s2_report", result)
    except _Problem as problem:
        raise _Problem(f"{_name(function)}, on {on}: {problem}") from None


def _check_report(obj) -> tuple[bool, str]:
    if not callable(obj):
        return _grade("s2_report", obj)
    for what, report, expected in REPORT_CASES:
        got = _summary(obj, report, what)
        tops = {cluster["name"] for cluster in report["clusters"] if cluster["parent_id"] is None}
        for field in _REPORT_KEYS:
            if got[field] == expected[field]:
                continue
            hint = ""
            if field == "highest_error_rate_subcategory" and got[field] in tops:
                hint = " That is a top-level category: a subcategory is a cluster whose `parent_id` is not None."
            elif field == "largest_category" and got[field] not in tops:
                hint = " That is a subcategory: a top-level category is a cluster whose `parent_id` is None."
            elif field == "largest_category_share":
                hint = " Divide by the conversations of the top-level categories only; the subcategories count the same conversations again."
            raise _Problem(f"{_name(obj)} is not right on {what}: `{field}` should be {_show(expected[field])}, it returned {_show(got[field])}.{hint}")
    value = _summary(obj, ts.load_insights_report(), "the sample Insights report")
    wrong = _wrong_fields("s2_report", value)
    if wrong:
        raise _Problem(
            f"{_name(obj)} passes the small test reports but is not right on the sample Insights report: "
            f"{_list([f'`{field}`' for field in wrong])}. It returned {', '.join(f'{field} = {_show(value[field])}' for field in wrong)}."
        )
    return True, VERIFIED + _PASS_TEXT["s2_report"](value) + f" {_name(obj)} also passes {len(REPORT_CASES)} small test reports."


def reference_evaluator() -> Callable:
    """The repo's reference `perform_eval`, loaded from `evaluators/online_evaluators.py` by path.

    Loading the file directly keeps the checker free of the `evaluators` package's other imports
    (LangChain, `config`), so a check starts in a fraction of a second.
    """
    loaded = sys.modules.get("evaluators.online_evaluators")
    if loaded is not None:
        return loaded.perform_eval
    path = REPO_ROOT / "evaluators" / "online_evaluators.py"
    spec = importlib.util.spec_from_file_location("m7_reference_online_evaluators", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.perform_eval


def _check_claim(obj) -> tuple[bool, str]:
    if not callable(obj):
        return _grade("s2_claim", obj)
    seed, labels, report = ts.load_seed(shift_to_now=False), ts.load_labels(), ts.load_insights_report()
    claim_name = ts.TOPICS["return_window"][2]  # "Return window questions"
    conversations = labels["conversations"]

    def count(name: str, evaluator: Callable, on: str) -> int:
        result = _call(obj, name, seed, labels, evaluator, on=on, definition=_CLAIM_DEFINITION)
        if isinstance(result, bool) or not isinstance(result, int):
            raise _Problem(f"{_name(obj)} must return a whole number (how many conversations are flagged); it returned {_show_python(result)} on {on}.")
        return result

    def flag_all(run, example=None):
        return {FEEDBACK_KEY: True}

    def flag_none(run, example=None):
        return {FEEDBACK_KEY: False}

    # Control 1: an evaluator that flags nothing must give 0 (catches a hard-coded number).
    got = count(claim_name, flag_none, f"'{claim_name}' with an evaluator that flags nothing")
    if got != 0:
        raise _Problem(f"{_name(obj)} returned {got} for an evaluator that flags nothing. Call the `perform_eval` you are given on the root runs of each conversation; do not hard-code the result.")
    # Control 2: a subcategory with two-turn conversations and an evaluator that flags everything:
    # the answer is the number of conversations, not the number of root runs.
    by_subcategory: dict[str, list[dict]] = {}
    for conversation in conversations:
        by_subcategory.setdefault(conversation["subcategory"], []).append(conversation)
    busy = max(by_subcategory, key=lambda name: sum(len(c["trace_keys"]) for c in by_subcategory[name]) - len(by_subcategory[name]))
    expected, turns = len(by_subcategory[busy]), sum(len(c["trace_keys"]) for c in by_subcategory[busy])
    got = count(busy, flag_all, f"'{busy}' with an evaluator that flags every run")
    if got != expected:
        hint = " That is the number of root runs: a conversation with two turns counts once." if got == turns and turns != expected else ""
        raise _Problem(f"{_name(obj)} returned {got} for '{busy}' with an evaluator that flags every run; that subcategory has {expected} conversations.{hint}")
    # Control 3: a subcategory the evaluator has nothing to say about.
    other = next(name for name in by_subcategory if name not in (claim_name, busy))
    got = count(other, reference_evaluator(), f"'{other}' with the reference evaluator")
    if got != 0:
        raise _Problem(f"{_name(obj)} returned {got} for '{other}'; no conversation of that subcategory is flagged. Count only the conversations whose `subcategory` equals `name`.")

    flagged = count(claim_name, reference_evaluator(), f"'{claim_name}' with the reference evaluator")
    cluster = next(c for c in report["clusters"] if c["name"] == claim_name)
    value = _normalise("s2_claim", {"conversations": cluster["num_runs"], "error_rate": cluster["stats"]["error_rate"], "flagged": flagged})
    if _wrong_fields("s2_claim", value):
        raise _Problem(f"{_name(obj)} passes the control cases but returned {flagged} for '{claim_name}' with the reference evaluator, which is not right.")
    return True, VERIFIED + _PASS_TEXT["s2_claim"](value) + f" {_name(obj)} also passes 3 control cases."


# ---------------------------------------------------------------------------------------------
# s3_triage and s3_assertions
# ---------------------------------------------------------------------------------------------

_TRIAGE_DEFINITION = EXERCISE_FILES["s3_triage"][2]


def _action(function, issue: dict, on: str) -> str:
    result = _call(function, copy.deepcopy(issue), on=on, definition=_TRIAGE_DEFINITION)
    if result not in ts.TRIAGE_ACTIONS:
        raise _Problem(f"{_name(function)} returned {_show_python(result)} on {on}. Return one of the four action codes: {', '.join(ts.TRIAGE_ACTIONS)}.")
    return result


def _issue_facts(issue: dict) -> str:
    fixes = len(issue.get("fixes") or [])
    return f"type {issue.get('type')}, status {issue.get('status')}, {fixes} {'entry' if fixes == 1 else 'entries'} in fixes"


def _check_triage(obj) -> tuple[bool, str]:
    if not callable(obj):
        if isinstance(obj, (list, tuple)):
            unknown = [action for action in obj if action not in ts.TRIAGE_ACTIONS]
            if unknown:
                raise _Problem(f"{_show_python(unknown[0])} is not an action code. Use: {', '.join(ts.TRIAGE_ACTIONS)}.")
        return _check_answer("s3_triage", obj)
    for what, issue, expected, why in TRIAGE_CASES:
        got = _action(obj, issue, what)
        if got != expected:
            raise _Problem(f"{_name(obj)} returned {got} for {what}; the next action is {expected}: {why}.")
    issues = ts.load_engine_issues()["issues"]
    actions = [_action(obj, issue, f"issue {number} on the board") for number, issue in enumerate(issues, start=1)]
    value = _normalise("s3_triage", {"actions": actions})
    if _wrong_fields("s3_triage", value):
        listing = "; ".join(f"issue {number} ({_issue_facts(issue)}) -> {action}" for number, (issue, action) in enumerate(zip(issues, actions), start=1))
        raise _Problem(
            f"{_name(obj)} passes the two extra cases but is not right for at least one of the three issues on the board. It returned: {listing}. "
            "Decide from `type`, `status` and `fixes`, not from the name or the severity."
        )
    return True, VERIFIED + _PASS_TEXT["s3_triage"](value) + f" {_name(obj)} also passes {len(TRIAGE_CASES)} extra cases."


def _check_assertions(obj) -> tuple[bool, str]:
    if isinstance(obj, dict):
        obj = obj.get("assertions", obj)
    if isinstance(obj, str) or not isinstance(obj, (list, tuple, set, frozenset)):
        raise _Problem("give the keys of the two assertions you picked, for example MY_ASSERTIONS = ['key_one', 'key_two'].")
    picked = list(obj)
    table = {row["key"]: row for row in assertion_table()}
    unknown = [key for key in picked if key not in table]
    if unknown:
        raise _Problem(f"{_show_python(unknown[0])} is not one of the six candidate keys: {', '.join(table)}.")
    if len(set(picked)) != 2:
        raise _Problem(f"pick exactly two assertions; you picked {len(set(picked))}.")
    for key in picked:
        row = table[key]
        if row["holds_for_recorded"] and row["holds_for_corrected"]:
            raise _Problem(f"`{key}` holds for the recorded answer too, so a test case with it would not have caught the wrong answer.")
        if not row["holds_for_corrected"]:
            raise _Problem(f"`{key}` fails for the corrected answer, so a correct agent would fail the test case.")
    return _grade("s3_assertions", {"assertions": sorted(set(picked))})


# ---------------------------------------------------------------------------------------------
# s4_masking
# ---------------------------------------------------------------------------------------------

MASKING_EMAIL = ts.PLANTED_EMAIL  # the synthetic address planted in the seed
MASKING_CONTROL = "ORD-2025-0050"  # an order id: not PII, so masking must leave it alone
MASKING_QUESTION = f"My email is {MASKING_EMAIL}. Where is order {MASKING_CONTROL}?"
MASKING_REPLY = f"I will email {MASKING_EMAIL} about order {MASKING_CONTROL}."
MASKING_SECOND_EMAIL = "returns.desk@techhub.example"  # a second synthetic address, to catch a rule written for one address
_MASKING_DEFINITION = EXERCISE_FILES["s4_masking"][2]
_NO_ANONYMIZER = object()


def masking_capture(anonymizer=_NO_ANONYMIZER) -> dict:
    """Trace one turn of a model-free agent with `PIIMiddleware` into the local recorder and count what would be uploaded.

    Returns `{"payloads", "with_email", "with_control"}`: the number of uploaded run payloads, and how
    many of them contain the customer's email address and the order id. With `anonymizer` the
    recorder's client is built as `Client(anonymizer=anonymizer)`. Nothing leaves the machine and no
    model is called: the reply is scripted (`utils.offline_capture.scripted_model`).
    """
    from langchain.agents import create_agent
    from langchain.agents.middleware import PIIMiddleware
    from langsmith import tracing_context

    from utils.offline_capture import count_payloads_containing, offline_client, scripted_model, uploaded_payloads

    agent = create_agent(
        scripted_model([MASKING_REPLY]),
        tools=[],
        middleware=[PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True)],
    )
    client, capture = offline_client() if anonymizer is _NO_ANONYMIZER else offline_client(anonymizer=anonymizer)
    with tracing_context(enabled=True, client=client):
        agent.invoke({"messages": [{"role": "user", "content": MASKING_QUESTION}]})
    client.flush()
    return {"payloads": len(uploaded_payloads(capture)), "with_email": count_payloads_containing(capture, MASKING_EMAIL),
            "with_control": count_payloads_containing(capture, MASKING_CONTROL)}


def _second_address_capture(anonymizer) -> dict:
    """Trace one plain function whose input and output contain a second address, through `Client(anonymizer=...)`."""
    from langchain_core.runnables import RunnableLambda
    from langsmith import tracing_context

    from utils.offline_capture import count_payloads_containing, offline_client, uploaded_payloads

    client, capture = offline_client(anonymizer=anonymizer)
    with tracing_context(enabled=True, client=client):
        RunnableLambda(lambda inputs: {"answer": f"Noted: {inputs['note']}"}, name="probe").invoke(
            {"note": f"Copy {MASKING_SECOND_EMAIL} on order {MASKING_CONTROL}."}
        )
    client.flush()
    return {"payloads": len(uploaded_payloads(capture)), "with_email": count_payloads_containing(capture, MASKING_SECOND_EMAIL),
            "with_control": count_payloads_containing(capture, MASKING_CONTROL)}


def _check_masking(obj) -> tuple[bool, str]:
    if not callable(obj):
        if isinstance(obj, dict) and "middleware_only" in obj and "middleware_only_more_than_zero" not in obj:
            obj = {**obj, "middleware_only_more_than_zero": isinstance(obj["middleware_only"], int) and obj["middleware_only"] > 0}
        return _grade("s4_masking", obj)

    from utils.offline_capture import refuse_non_local_connects

    with refuse_non_local_connects() as attempts:
        base = masking_capture()
        leak = f"With PIIMiddleware alone, {base['with_email']} of {base['payloads']} uploaded payloads contain {MASKING_EMAIL}."
        if base["with_email"] == 0 or base["with_control"] == 0:
            raise _Problem(
                "the checker's own baseline no longer shows the leak (with the middleware alone, "
                f"{base['with_email']} of {base['payloads']} payloads contain the email). The installed LangChain version behaves "
                "differently from the one this check was written for; tell your instructor."
            )
        try:
            anonymizer = obj()
        except NotImplementedError:
            raise _Problem(
                f"{leak} {_name(obj)} is not implemented yet: it still raises NotImplementedError. Write {_MASKING_DEFINITION} in "
                "masking.py so that it returns an anonymizer, then run this check again."
            ) from None
        except SystemExit:
            raise _Problem(f"{leak} {_name(obj)}() called sys.exit() (it raised SystemExit). {_EXIT_ADVICE}") from None
        except Exception as exc:  # noqa: BLE001
            raise _Problem(f"{leak} {_name(obj)}() raised {_describe(exc)}.") from None
        if not callable(anonymizer):
            raise _Problem(
                f"{leak} {_name(obj)}() must return an anonymizer: a function to pass as Client(anonymizer=...), for example the result of "
                f"langsmith.anonymizer.create_anonymizer([...]). It returned {type(anonymizer).__name__}."
            )
        masked = masking_capture(anonymizer)
        if masked["payloads"] != base["payloads"]:
            raise _Problem(
                f"with your anonymizer the client uploaded {masked['payloads']} payloads where {base['payloads']} are expected. The anonymizer "
                "probably raises or returns nothing: it must return the data it is given, with the addresses replaced."
            )
        if masked["with_email"] > 0:
            raise _Problem(f"{leak} With your anonymizer, {masked['with_email']} of {masked['payloads']} still contain it; the target is 0.")
        if masked["with_control"] != base["with_control"]:
            raise _Problem(
                f"the email address is gone, but so is text that is not PII: the order id {MASKING_CONTROL} is in {base['with_control']} payloads "
                f"without your anonymizer and in {masked['with_control']} with it. Mask the address only; hiding everything does not pass."
            )
        second = _second_address_capture(anonymizer)
        if second["with_email"] > 0 or second["with_control"] != second["payloads"]:
            what = f"{MASKING_SECOND_EMAIL} is still in {second['with_email']} of {second['payloads']} payloads" if second["with_email"] else f"the order id next to {MASKING_SECOND_EMAIL} was removed"
            raise _Problem(f"your anonymizer masks {MASKING_EMAIL}, but on a second address it is not right: {what}. Match the pattern of an email address, not one address.")
    if attempts:
        raise _Problem(f"your code tried to open a network connection ({attempts[0]}). An anonymizer runs locally, before the upload.")
    value = {"middleware_only_more_than_zero": base["with_email"] > 0, "with_anonymizer": masked["with_email"],
             "control_string_unchanged": masked["with_control"] == base["with_control"]}
    detail = (f"Measured here: {base['with_email']} of {base['payloads']} payloads with the middleware alone, {masked['with_email']} of "
              f"{masked['payloads']} with your anonymizer; a second address is masked too.")
    return _grade("s4_masking", value, detail)


# ---------------------------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------------------------

_CHECKS: dict[str, Callable[[Any], tuple[bool, str]]] = {
    "setup": _check_setup,
    "s1_evaluator": _check_evaluator,
    "s2_report": _check_report,
    "s2_claim": _check_claim,
    "s3_triage": _check_triage,
    "s3_assertions": _check_assertions,
    "s4_masking": _check_masking,
}


def _check_answer(exercise_id: str, obj) -> tuple[bool, str]:
    """The ids whose answer is a value computed in a notebook cell: a dictionary, or the bare value of a single field."""
    field = _SINGLE_FIELD.get(exercise_id)
    if field and not isinstance(obj, dict):
        if exercise_id == "s1_routing" and isinstance(obj, (list, tuple, set)):
            obj = len(obj)  # the selected runs themselves
        if exercise_id == "s4_routes" and isinstance(obj, str):
            obj = obj.rstrip("/")
        obj = {field: obj}
    elif exercise_id == "s4_routes" and isinstance(obj, dict) and isinstance(obj.get("base_url"), str):
        obj = {**obj, "base_url": obj["base_url"].rstrip("/")}
    return _grade(exercise_id, obj)


def check(exercise_id: str, obj: Any = None) -> tuple[bool, str]:
    """Check one exercise of Module 7. Returns `(ok, message)` and never raises.

    `exercise_id` is one of `EXERCISE_IDS` (the checker ids of the module, plus `setup`). `obj` is
    the learner's function for the exercises that are functions, or the answer as a dictionary
    with the fields listed in `ANSWER_FIELDS[exercise_id]`; the module docstring lists both forms.

    On success `message` starts with "✅ Verified: " and states the verified values. On failure it
    names the field or the test case that is wrong and never prints the answer key. The comparison
    uses `data/answers.json`, or `data/answer_hashes.json` when the answer file has been removed.
    """
    try:
        if exercise_id not in EXERCISE_IDS:
            return False, f"unknown exercise id {exercise_id!r}. Known ids: {', '.join(EXERCISE_IDS)}."
        if obj is None and exercise_id != "setup":
            return False, f"nothing to check for {exercise_id}: pass your function or your answer as the second argument."
        return _CHECKS.get(exercise_id, lambda value: _check_answer(exercise_id, value))(obj)
    except _Problem as problem:
        return False, str(problem)
    except SystemExit:  # raised somewhere `_call` does not reach, for example inside an anonymizer while a trace is uploaded
        return False, f"your code called sys.exit() (it raised SystemExit) while {exercise_id} was being checked. {_EXIT_ADVICE}"
    except Exception as exc:  # noqa: BLE001 - a checker that raises would stop a notebook or fail a track with a traceback
        # A truncated seed file or a label file without its keys ends here. That is a damaged data file, not a bug.
        damaged = _data_problem()
        if damaged:
            return False, damaged
        return False, f"the checker itself failed on {exercise_id} ({type(exc).__name__}: {exc}). This is a bug in the checker, not in your answer; tell your instructor."


# ---------------------------------------------------------------------------------------------
# Loading a learner's function from an exercise file, and the command line
# ---------------------------------------------------------------------------------------------

# Top-level statements of an exercise file that the loader does not execute: a bare expression (a
# `print`, a test call), an `assert` and a `raise`. Everything else runs, as it does on import:
# imports, assignments, `def`, `class`, and blocks such as `if`, `for`, `try` and `with`. An
# `if __name__ == "__main__":` block is kept too and does nothing, because `__name__` is not "__main__".
_SKIPPED = (ast.Expr, ast.Assert, ast.Raise)


def _load_exercise(exercise_id: str, folder: str | Path | None = None) -> tuple[Callable, list[int], ast.FunctionDef | None]:
    """Load one exercise file. Returns `(function, skipped lines, the function's top-level def)`.

    `skipped lines` are the line numbers of the top-level statements that were not executed (see
    `_SKIPPED`); a docstring or another bare constant has no effect and is not listed. The third
    value is the `ast` node of the function's own top-level `def`, or `None` when the name was
    bound in another way (an assignment, a `def` inside an `if`).
    """
    file_name, function_name, definition = EXERCISE_FILES[exercise_id]
    path = Path(folder or EXERCISES_DIR) / file_name
    if not path.is_file():
        restore = f"{_display(EXERCISES_DIR)}/{file_name}"
        raise _Problem(f"{file_name} is missing from {_display(path.parent)}. Restore that one file (for example with `git checkout -- {restore}`) and try again.")
    try:
        # "utf-8-sig": a byte order mark at the start of the file (some editors write one) is valid Python and is dropped here.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        raise _Problem(f"{file_name} has a syntax error on line {exc.lineno}: {exc.msg}. Fix it and run this check again.") from None
    kept = [node for node in tree.body if not isinstance(node, _SKIPPED)]
    skipped = [node.lineno for node in tree.body if isinstance(node, _SKIPPED) and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    namespace: dict = {"__name__": f"m7_exercise_{path.stem}", "__file__": str(path)}
    try:
        # dont_inherit: without it the learner's code would be compiled with this module's
        # `from __future__ import annotations`, and an annotation that needs a missing name would never be evaluated.
        exec(compile(ast.Module(body=kept, type_ignores=[]), str(path), "exec", dont_inherit=True), namespace)  # noqa: S102 - the learner's own exercise file
    except SystemExit:
        raise _Problem(f"{file_name} could not be loaded: its top-level code called sys.exit() (it raised SystemExit). Remove that call, or move it under `if __name__ == \"__main__\":`.") from None
    except Exception as exc:  # noqa: BLE001
        raise _Problem(f"{file_name} could not be loaded: {_describe(exc)}.{_skipped_note(file_name, skipped)}") from None
    function = namespace.get(function_name)
    if not callable(function):
        raise _Problem(f"{file_name} does not define {function_name}. Define it as {definition}.")
    own_def = next((node for node in reversed(tree.body) if isinstance(node, ast.FunctionDef) and node.name == function_name), None)
    return function, skipped, own_def


def load_exercise_function(exercise_id: str, folder: str | Path | None = None) -> Callable:
    """Load the function for `exercise_id` from its exercise file in `folder` (default: the module's `exercises/` folder).

    The file is parsed with `ast`. Its imports, assignments, functions, classes and blocks (`if`,
    `for`, `try`, `with`) are executed; a bare top-level expression (a `print`, a test call), an
    `assert` and a `raise` are not, and an `if __name__ == "__main__":` block does nothing, so
    what a learner leaves at the bottom of the file to try the function out does not run during
    a check. Raises `_Problem` (a message for the learner) when the file is missing, has a syntax
    error, cannot be loaded, or does not define the function.
    """
    return _load_exercise(exercise_id, folder)[0]


def _skipped_note(file_name: str, skipped: list[int]) -> str:
    """One sentence for a failed check of a file whose top level has statements the loader did not run, else an empty string."""
    if not skipped:
        return ""
    lines = f"line {skipped[0]}" if len(skipped) == 1 else "lines " + _list([str(line) for line in skipped[:6]]) + (" and more" if len(skipped) > 6 else "")
    return (
        f" Note: the check did not run {lines} of {file_name}. It runs a file's imports, assignments, definitions and if/for/try/with "
        "blocks, but not a bare top-level call, assert or raise. If your function needs what such a line does, move it into the function."
    )


def _is_standard_library(module: str) -> bool:
    return module.split(".")[0] in sys.stdlib_module_names


def _foreign_imports(own_def: ast.FunctionDef) -> list[str]:
    """What the function imports that is not a module of Python's standard library, in the order written.

    Read from the source with `ast`: `import x`, `from x import y`, a relative import, and a call
    to `__import__(...)` or `importlib.import_module(...)` (a module name that is not a plain
    string is listed as "a module chosen at run time"). Such an import succeeds here, because the
    repository root and its installed packages are on the import path, and fails where LangSmith
    runs the function. This reads what is written; it does not stop code that hides an import
    (in `exec`, for example).
    """
    found: list[str] = []

    def note(name: str) -> None:
        if name not in found:
            found.append(name)

    for node in ast.walk(own_def):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_standard_library(alias.name):
                    note(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # `from . import x`, `from ..utils import y`: relative to a package that is not there
                note("." * node.level + (node.module or ""))
            elif not _is_standard_library(node.module or ""):
                note(node.module or "")
        elif isinstance(node, ast.Call):
            target = node.func
            by_name = isinstance(target, ast.Name) and target.id == "__import__"
            by_attribute = isinstance(target, ast.Attribute) and target.attr in ("import_module", "__import__")
            if not (by_name or by_attribute):
                continue
            module = node.args[0] if node.args else next((keyword.value for keyword in node.keywords if keyword.arg == "name"), None)
            if isinstance(module, ast.Constant) and isinstance(module.value, str):
                if module.value.startswith(".") or not _is_standard_library(module.value):
                    note(module.value)
            else:
                note("a module chosen at run time")
    return found


def _standalone_problem(file_name: str, function_name: str, definition: str, own_def: ast.FunctionDef | None, path: Path) -> str | None:
    """Check `perform_eval` once more from its own source alone. Returns a failure message, or `None` when it passes.

    LangSmith runs the source of a code evaluator by itself: the function is pasted into the Code
    Evaluator editor without the rest of the file, and without this repository. So three things
    are checked here: the function is a top-level `def`; its body imports nothing outside the
    standard library (`_foreign_imports`); and the `def`, compiled alone with nothing else from
    the file in scope, passes the same check as the function inside its file.

    The exercise allows the standard library only. LangSmith's documented evaluator sandbox also
    has a few data packages (numpy, pandas and others) in versions of its own; the exercise does
    not need them, so they are not allowed here either.
    """
    why = "LangSmith runs the source of a code evaluator on its own, without the rest of this file."
    if own_def is None:
        return (
            f"{function_name} passes, but {file_name} does not define it with a `def` at the top level of the file, so its source cannot be "
            f"pasted into LangSmith on its own. Write it as `def {definition}:` at the top level."
        )
    foreign = _foreign_imports(own_def)
    if foreign:
        return (
            f"{function_name} passes here, but it imports {_list(foreign)}, which {'is' if len(foreign) == 1 else 'are'} not part of Python's "
            "standard library. LangSmith runs a code evaluator without this repository and without the packages installed here, so that "
            "import fails there. Use the standard library only (`re`, for example) and write the rule inside the function."
        )
    namespace: dict = {"__name__": "m7_code_evaluator"}
    try:
        # dont_inherit: see `_load_exercise`. Annotations are evaluated here as they are where the function is pasted alone.
        exec(compile(ast.Module(body=[own_def], type_ignores=[]), str(path), "exec", dont_inherit=True), namespace)  # noqa: S102 - the learner's own function
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - a decorator, a default value or an annotation that needs a name from the file
        return (
            f"{function_name} passes inside {file_name}, but its definition cannot be run on its own ({_describe(exc)}). {why} "
            "Use no decorator, no default value and no type annotation that needs a name from outside the function."
        )
    ok, message = check("s1_evaluator", namespace[function_name])
    if ok:
        return None
    return (
        f"{function_name} passes inside {file_name}, but not when its source is run on its own: {message} {why} "
        "Move every import, constant and helper function it uses inside the function body."
    )


def _display(path: Path) -> str:
    """A path for a message: relative to the repository root when it is inside it."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def check_file(exercise_id: str, folder: str | Path | None = None) -> tuple[bool, str]:
    """Check one of `COMMAND_LINE_IDS` from the files on disk. Returns `(ok, message)` and never raises.

    For the five function exercises the function is loaded from its file in `folder` (see
    `load_exercise_function`); `setup` reads the state file instead. Anything the learner's code
    prints is swallowed, so the caller can print exactly one line.

    Two things happen here and not in `check`, because they need the file: `s1_evaluator` is
    checked a second time from the function's own source alone (see `_standalone_problem`), and a
    failure message ends with a note when the loader skipped top-level lines of the file.

    Before a function exercise is loaded, the generated data files are compared with a fresh
    generation (`changed_data_files`). If one is missing or was changed, the check stops with a
    message that names it and the command that restores it. The `setup` check makes its own
    comparison of the seed file.
    """
    if exercise_id not in COMMAND_LINE_IDS:
        if exercise_id in EXERCISE_IDS:
            return False, f"{exercise_id} is checked inside its notebook, not from the command line. From the command line: {', '.join(COMMAND_LINE_IDS)}."
        return False, f"unknown exercise id {exercise_id!r}. Use one of: {', '.join(COMMAND_LINE_IDS)}."
    file_name, function_name, definition = EXERCISE_FILES.get(exercise_id, ("", "", ""))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if exercise_id == "setup":
                return check("setup", None)
            damaged = _data_problem()
            if damaged:
                return False, damaged
            try:
                function, skipped, own_def = _load_exercise(exercise_id, folder)
            except _Problem as problem:
                return False, str(problem)
            ok, message = check(exercise_id, function)
            if ok and exercise_id == "s1_evaluator":
                problem = _standalone_problem(file_name, function_name, definition, own_def, Path(folder or EXERCISES_DIR) / file_name)
                if problem:
                    ok, message = False, problem
            return ok, message if ok else message + _skipped_note(file_name, skipped)
    except SystemExit:  # `check` reports this itself; this is for an exit raised in between, so that no id ends without a result
        return False, f"your code called sys.exit() (it raised SystemExit) while {exercise_id} was being checked. {_EXIT_ADVICE}"


_USAGE = """usage: check.py <id> [<id> ...]
       check.py --list
       check.py --restore-data

Checks one or more Module 7 exercises and prints one line per id: "PASS: ..." or "FAIL: ...".
Exit code 0 when every check passes, 1 when one fails, 2 for a wrong id or no id.
The exercise files are read from the folder in the environment variable M7_EXERCISES_DIR
(default: the folder that holds check.py).

--restore-data regenerates the data files of workshop_modules/module_7/data that are missing or
were changed (the seed, its labels, the sample report and the sample issue board). It does not
touch the exercise files, and it writes answers.json only where that file already exists."""


def main(argv: list[str] | None = None, default_folder: str | Path | None = None) -> int:
    """The command line behind `workshop_modules/module_7/exercises/check.py`. Returns the exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(errors="replace")  # a terminal without UTF-8 must not turn a message into a traceback
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0 if argv else 2
    if argv[0] == "--list":
        print("setup           the state file written by scripts/module7_connect_langsmith.py")
        for exercise_id, (file_name, _, definition) in EXERCISE_FILES.items():
            print(f"{exercise_id:<15} {file_name}: {definition}")
        return 0
    if argv[0] == "--restore-data":
        if len(argv) > 1:
            print("FAIL: --restore-data takes no id. Run it alone, then run the check.")
            return 2
        try:
            restored = restore_data_files()
        except Exception as exc:  # noqa: BLE001 - the generator reads the TechHub database and documents
            print(f"FAIL: the data files could not be regenerated ({_describe(exc)}). Tell your instructor.")
            return 1
        if restored:
            print(f"Restored {_list([f'{_DATA_REL}/{name}' for name in restored])} from the generator.")
        else:
            print(f"Nothing to restore: the data files in {_DATA_REL} are intact.")
        return 0
    folder = os.environ.get("M7_EXERCISES_DIR") or default_folder or EXERCISES_DIR
    code = 0
    for exercise_id in argv:
        ok, message = check_file(exercise_id, folder)
        message = " ".join(message.removeprefix(VERIFIED).split())
        if ok:
            print(f"PASS: {message}")
        else:
            print(f"FAIL: {message}")
            code = max(code, 2 if exercise_id not in COMMAND_LINE_IDS else 1)
    return code
