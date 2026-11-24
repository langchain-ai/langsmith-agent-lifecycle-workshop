"""One synthetic day of TechHub production traffic for Module 7: generate it, load it, read it.

Module 7 teaches monitoring on a fixed data set, the "seed": 200 conversations (260 traces) of the
deep support agent over 20 hours, with five planted incidents. This file is the only place where
that data is defined. Nothing here calls a model, LangSmith or the network, and nothing is recorded
from a real system: every run is built from templates, filled with real customer, order and
product ids from `data/structured/techhub.db` and with text from `data/documents/`.

    seed = load_seed()                 # the committed seed, timestamps shifted so the newest trace is 5 minutes old
    describe(seed)                     # one paragraph of counts
    print_trace(seed, "t-0042")        # one trace as a tree

What a seed is (a plain dictionary):

    seed["meta"]      constants of the data set (versions, clock, sampling constant, illustrative prices)
    seed["runs"]      a flat list of run dictionaries in the shape LangSmith ingests:
                      id, trace_id, parent_run_id, dotted_order, name, run_type, start_time, end_time,
                      inputs, outputs, error, extra (with extra["metadata"]), tags
    seed["feedback"]  one `user_score` (1 thumbs-up, 0 thumbs-down) per rated conversation, on its last root run

On disk the runs are grouped by trace, and the values every run of a trace shares (the caller
metadata, the tags, the trace id) are stored once per trace to keep the file small. `load_seed()`
puts them back on every run, so always read the file through `load_seed()`.

Every run carries the tag `seed:m7` and the metadata `synthetic: true`. Trees are "lite": the 14
meaningful runs of a delegated lookup, without the roughly 80 middleware spans a live trace of the
same agent adds, and with long strings (system prompts, search results) shortened and marked as such. A root run that failed has `error` set and empty outputs (`{}`), which is what the
LangChain tracer records for a failed run; every other root run has `messages` in its inputs and outputs.

Ground truth that a real project would not have (the topic of each conversation, which incident it
belongs to) is kept out of the runs on purpose. It lives in `seed_labels.json`, which is never uploaded.

Maintainers: `scripts/module7_seed.py build` writes the seven data files of
`workshop_modules/module_7/data/` from `generate_seed()`; `scripts/module7_seed.py verify` regenerates
them and compares bytes. Every count is built by construction and asserted before `generate_seed()`
returns, so a change that breaks a number in the notebooks fails here first. The design constants are
sections 6.2, 6.3 and 6.6 of `docs/2026-11-19-module-7-monitoring-governance-prd.md`.

Standard library only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
import sqlite3
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "workshop_modules" / "module_7" / "data"
DB_PATH = REPO_ROOT / "data" / "structured" / "techhub.db"
DOCS = REPO_ROOT / "data" / "documents"

SEED_FILE = "techhub_production_day.json"
LABELS_FILE = "seed_labels.json"
ANSWERS_FILE = "answers.json"
HASHES_FILE = "answer_hashes.json"
FOLLOWUP_FILE = "followup_traces.json"
INSIGHTS_FILE = "insights_report_techhub.json"
ENGINE_FILE = "engine_issues_techhub.json"
DATA_FILES = (SEED_FILE, LABELS_FILE, ANSWERS_FILE, HASHES_FILE, FOLLOWUP_FILE, INSIGHTS_FILE, ENGINE_FILE)

# ---------------------------------------------------------------------------------------------
# Design constants (PRD sections 6.2, 6.3, 6.6). Change one only together with the PRD and the slides.
# ---------------------------------------------------------------------------------------------

RNG_SEED = 7
ROOT_RUN_NAME = "deep_support_agent"  # the Module 4 agent's root run name
LLM_RUN_NAME = "ChatOpenAI"  # LLM runs are named after the model class
MAIN_MODEL, SMALL_MODEL = "gpt-5.4", "gpt-5.4-mini"
SEED_TAG = "seed:m7"
FOLLOWUP_TAG = "followup:m7"
DEFAULT_PROJECT = "techhub-deep-agent-production"
ENVIRONMENT = "production"

# The seed's own clock. `load_seed()` shifts everything so SEED_END lands 5 minutes before "now".
SEED_END = datetime(2026, 11, 19, 9, 0, 0, tzinfo=timezone.utc)  # start of the newest root run
SPAN = timedelta(hours=20)
NEW_VERSION_SPAN = timedelta(hours=8)  # 1.5.0 serves the last 8 hours
SEED_START = SEED_END - SPAN
RELEASE_AT = SEED_END - NEW_VERSION_SPAN
NEWEST_RUN_AGE = timedelta(minutes=5)

OLD_VERSION, NEW_VERSION, FIXED_VERSION = "1.4.0", "1.5.0", "1.5.1"
# Invented commit ids. `revision_id` is the key Engine uses to tie a trace to a commit.
REVISIONS = {OLD_VERSION: "a1b2c3d", NEW_VERSION: "e4f5a6b", FIXED_VERSION: "c7d8e9f"}
# The sentence release 1.5.0 added to the product-policy-specialist's instructions (incident A).
PLANTED_INSTRUCTION = "Customers have 30 days from delivery to return any item."

N_CONVERSATIONS, N_ROOT_RUNS, N_TWO_TURN = 200, 260, 60
CONVERSATIONS_BY_VERSION = {OLD_VERSION: 120, NEW_VERSION: 80}
ROOT_RUNS_BY_VERSION = {OLD_VERSION: 156, NEW_VERSION: 104}

# topic: (conversations on 1.4.0, on 1.5.0, subcategory name, category name)
TOPICS: dict[str, tuple[int, int, str, str]] = {
    "where_is_my_order": (26, 20, "Where is my order", "Order status and tracking"),
    "order_not_found": (13, 6, "Order reported as not found", "Order status and tracking"),
    "order_contents": (8, 5, "What is in my order", "Order status and tracking"),
    "return_window": (11, 16, "Return window questions", "Returns and refunds"),
    "refund_approval": (10, 6, "Refund requests awaiting approval", "Returns and refunds"),
    "refund_timing": (6, 3, "When will my refund arrive", "Returns and refunds"),
    "compatibility": (16, 9, "Compatibility between products", "Product specs and compatibility"),
    "spec_lookup": (12, 7, "Single-product spec lookups", "Product specs and compatibility"),
    "other_customer_data": (7, 4, "Asks for another customer's data", "Out of scope or adversarial"),
    "unrelated": (11, 4, "Unrelated requests", "Out of scope or adversarial"),
}
CATEGORY_ORDER = (
    "Order status and tracking",
    "Returns and refunds",
    "Product specs and compatibility",
    "Out of scope or adversarial",
)
# Conversations with a second turn: topic -> ((delegated, direct) on 1.4.0, (delegated, direct) on 1.5.0).
# A delegated second turn is a follow-up question that needs a lookup (14 runs); a direct one is answered by the
# main agent from the conversation so far (3 runs). 12 delegated and 48 direct in total.
TWO_TURN: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "where_is_my_order": ((4, 9), (3, 6)),
    "order_contents": ((1, 2), (1, 2)),
    "refund_timing": ((1, 2), (0, 2)),
    "compatibility": ((0, 6), (0, 3)),
    "spec_lookup": ((1, 3), (1, 3)),
    "unrelated": ((0, 4), (0, 2)),
    "other_customer_data": ((0, 3), (0, 1)),
}

# Incident A: of the 27 return-window conversations 15 are about opened items.
OPENED_BY_VERSION = {OLD_VERSION: 4, NEW_VERSION: 11}  # the 11 on 1.5.0 get the wrong window
UNOPENED_BY_VERSION = {OLD_VERSION: 7, NEW_VERSION: 5}
WRONG_RETURN_WINDOW_SCORES = {"up": 9, "none": 2, "down": 0}
# Incident B: 13 errored root runs. 8 in one burst, 5 in the background.
BURST_ERRORS, BACKGROUND_ERRORS = 8, 5
BURST_STARTS_BEFORE_END = timedelta(minutes=52)  # the burst lies 52 to 49 minutes before the newest run
BURST_WINDOW_SECONDS = 180
ALERT_WINDOW_SECONDS = 300
BURST_ERROR = "OrderServiceUnavailable: get_order_status timed out"
LOCK_ERROR = "sqlite3.OperationalError: database is locked"
SEARCH_ERROR = "TimeoutError: {tool} timed out"
# Incident C: thumbs-down on 16 of the 19 "not found" conversations (12 on 1.4.0, 4 on 1.5.0).
NOT_FOUND_DOWN = {OLD_VERSION: 12, NEW_VERSION: 4}
BURST_DOWN, OTHER_DOWN = 6, 3  # 6 thumbs-down in the burst (1.5.0), 3 elsewhere (1.4.0)
SCORES = {"up": 145, "down": 25, "none": 30}
# Incident D: one corporate customer asks 9 of the 25 compatibility questions.
TOP_SPENDER, TOP_SPENDER_COMPATIBILITY = "CUST-010", 9
# Incident E: one email address typed by a customer. Synthetic, on a reserved example domain.
PLANTED_EMAIL = "jordan.lee@example.com"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# Sampling exercise (Section 1): a fixed 25% draw of the 260 root runs scores 65 and catches 3 of the 11.
SAMPLING_RATE = 0.25
SAMPLING_SEED = 3  # a seed for which the draw catches exactly 3 (`_find_sampling_seed` lists the smallest); asserted by `generate_seed`
SAMPLED_RUNS, SAMPLED_CAUGHT = 65, 3

# ILLUSTRATIVE prices in US dollars per 1 million tokens. They are invented round numbers for the
# cost arithmetic of this lab, not a provider's price list. Whether LangSmith prices these model
# names in a given workspace is unverified, so the lab computes cost locally from token counts.
ILLUSTRATIVE_PRICES_PER_1M = {
    MAIN_MODEL: {"input": 2.50, "output": 10.00},
    SMALL_MODEL: {"input": 1.00, "output": 4.00},
}
# Spend-cap sketch (Section 4, 120-minute path). At the illustrative prices the day's model calls cost
# 4.92 US dollars. A daily cap of half that, 2.46, is crossed by model call 473 of 934 in time order:
# that call still succeeds, and the 461 after it get a 402.
DAY_SPEND_USD, DAILY_CAP_USD = 4.92, 2.46
MODEL_CALLS, CAP_CROSSING_CALL = 934, 473

CALLER_METADATA_KEYS = (
    "thread_id",
    "customer_id",
    "customer_segment",
    "app_version",
    "environment",
    "revision_id",
    "lc_agent_name",
    "seed_trace_key",
    "synthetic",
)

# Names the Section 3 exercises share with the checker and the notebooks.
TRIAGE_ACTIONS = ("apply_fix_and_add_examples", "review_pull_request", "save_for_later", "close_incorrectly_flagged")
ASSERTION_KEYS = ("states_14_day_window", "no_30_day_claim")  # the two assertions that separate the wrong answer from the corrected one
SEVERITY_LABELS = {0: "urgent", 1: "high", 2: "medium", 3: "low"}  # Engine issue `severity`, from the REST schema

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_DOTTED_SEGMENT = re.compile(r"^\d{8}T\d{12}Z[0-9a-f-]{36}$")


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------


class _Rng:
    """Random choices built only on `random.Random(seed).random()`.

    Python guarantees that `random()` returns the same sequence for the same seed in every version;
    it does not guarantee that for `choice`, `shuffle` or `sample`. Using only `random()` keeps the
    generated files byte-identical across Python versions.
    """

    def __init__(self, seed: int):
        self._r = random.Random(seed)

    def rand(self) -> float:
        return self._r.random()

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self._r.random()

    def below(self, n: int) -> int:
        return min(int(self._r.random() * n), n - 1)

    def choice(self, items):
        return items[self.below(len(items))]

    def shuffled(self, items) -> list:
        keyed = [(self._r.random(), i) for i in range(len(items))]
        return [items[i] for _, i in sorted(keyed)]

    def hex(self, n: int) -> str:
        return "".join("0123456789abcdef"[self.below(16)] for _ in range(n))


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="microseconds")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso_z(dt: datetime) -> str:
    """Second-resolution timestamp with a Z suffix, the form the Insights and Engine REST schemas show."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uuid7_int(dt: datetime, rand_a: int, rand_b: int) -> str:
    ms = (dt - _EPOCH) // timedelta(milliseconds=1)
    value = (ms << 80) | (7 << 76) | ((rand_a & 0xFFF) << 64) | (0b10 << 62) | (rand_b & ((1 << 62) - 1))
    return str(uuid.UUID(int=value))


def _uuid7(dt: datetime, rng: _Rng) -> str:
    """A UUID version 7 for `dt` with random bits from the seeded generator (reproducible)."""
    return _uuid7_int(dt, rng.below(1 << 12), (rng.below(1 << 31) << 31) | rng.below(1 << 31))


def uuid7_at(dt: datetime) -> str:
    """A UUID version 7 whose timestamp is `dt`, with fresh random bits. Standard library only."""
    fresh = uuid.uuid4().int
    return _uuid7_int(dt, fresh >> 100, fresh)


def _clip(text: str, limit: int) -> str:
    """Shorten a long string and say so, the way the research capture marks removed text."""
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()} ...<truncated, {len(text)} chars>"


def _round_half_up(value: float, places: int) -> float:
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def canonical_json(value: Any) -> str:
    """The one text form of an answer that `answer_hashes.json` is computed from."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# Source data: the TechHub database and documents
# ---------------------------------------------------------------------------------------------


def _load_source() -> dict:
    """Read customers, orders, items, products and the document excerpts the templates quote."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        customers = {cid: seg for cid, seg in con.execute("SELECT customer_id, segment FROM customers ORDER BY customer_id")}
        products = {
            pid: {"id": pid, "name": name, "category": category, "price": price}
            for pid, name, category, price in con.execute("SELECT product_id, name, category, price FROM products ORDER BY product_id")
        }
        orders: dict[str, dict] = {}
        for oid, cid, date, status, shipped, tracking in con.execute(
            "SELECT order_id, customer_id, order_date, status, shipped_date, tracking_number FROM orders ORDER BY order_id"
        ):
            orders[oid] = {"id": oid, "customer_id": cid, "date": date, "status": status, "shipped": shipped, "tracking": tracking, "items": []}
        for oid, pid, quantity, price in con.execute("SELECT order_id, product_id, quantity, price_per_unit FROM order_items ORDER BY order_item_id"):
            orders[oid]["items"].append({"product_id": pid, "quantity": quantity, "price": price})
    finally:
        con.close()
    by_customer: dict[str, list[dict]] = {cid: [] for cid in customers}
    for order in orders.values():
        by_customer[order["customer_id"]].append(order)

    policy = (DOCS / "policies" / "return_policy.md").read_text(encoding="utf-8")
    guide = (DOCS / "policies" / "compatibility_guide.md").read_text(encoding="utf-8")
    specs: dict[str, list[tuple[str, str]]] = {}
    compatibility: dict[str, str] = {}
    for pid in products:
        text = (DOCS / "products" / f"{pid}.md").read_text(encoding="utf-8")
        compatibility[pid] = _section(text, "## Compatibility")
        specs[pid] = re.findall(r"^- \*\*([^*:]+):\*\* (\S.*)$", _section(text, "## Key Specifications"), flags=re.M)
    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "by_customer": by_customer,
        "return_windows": "[return_policy]\n## Return Windows\n\n" + _section(policy, "## Return Windows"),
        "refund_method": "[return_policy]\n## Refund Method\n\n" + _section(policy, "## Refund Method"),
        "guide": guide,
        "specs": specs,
        "compatibility": compatibility,
    }


def _section(markdown: str, heading: str) -> str:
    """The text under one `## ` heading of a Markdown document."""
    match = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", markdown, flags=re.M | re.S)
    if not match:
        raise ValueError(f"heading {heading!r} not found")
    return match.group(1).strip()


def _guide_block(guide: str, header: str) -> str:
    """One bold-headed bullet block of the compatibility guide, as a search result would return it."""
    match = re.search(rf"^\*\*{re.escape(header)}:\*\*\n((?:- .*\n?)+)", guide, flags=re.M)
    if not match:
        raise ValueError(f"compatibility guide block {header!r} not found")
    return f"[compatibility_guide]\n**{header}:**\n{match.group(1).strip()}"


# What the real tools in tools/database.py return, reproduced from the same rows.
def _fmt_order_status(order: dict) -> str:
    text = f"Order {order['id']}:\n- Status: {order['status']}\n- Order Date: {order['date']}\n"
    if order["shipped"]:
        text += f"- Shipped Date: {order['shipped']}\n"
    if order["tracking"]:
        text += f"- Tracking Number: {order['tracking']}\n"
    return text


def _fmt_order_items(order: dict) -> str:
    return f"Items in order {order['id']}:\n" + "".join(f"- Product ID: {i['product_id']}, Quantity: {i['quantity']}\n" for i in order["items"])


def _fmt_customer_orders(orders: list[dict]) -> str:
    recent = sorted(orders, key=lambda o: (o["date"], o["id"]), reverse=True)
    return "Recent orders:\n" + "".join(f"- {o['id']}: {o['date']}, {o['status']}\n" for o in recent)


def _fmt_item_price(order: dict, item: dict) -> str:
    return f"Historical price for {item['product_id']} in {order['id']}: ${item['price']:.2f} per unit (quantity: {item['quantity']})"


# ---------------------------------------------------------------------------------------------
# Wording. Randomness chooses among these; it never changes a count.
# ---------------------------------------------------------------------------------------------

# The first lines of the real prompts (agents/deep_support_agent.py), shortened: a live main-agent prompt has about 9,000 characters.
MAIN_SYSTEM = (
    "You are TechHub's customer support agent.\nFollow the operating guide in your memory (AGENTS.md) and use your "
    "skills when a task matches them.\n\nVerified customer for this conversation: {customer_id}. ...<truncated>"
)
ORDER_SYSTEM = (
    "You are TechHub's order specialist. Use your tools to answer precisely. Report exactly what the tools return; "
    "if a tool refuses access, say so plainly.\n\nVerified customer for this conversation: {customer_id}."
)
POLICY_SYSTEM = (
    "You are TechHub's product and policy specialist. Search the documents and quote the specific policy terms or "
    "specs that answer the question, naming the source document."
)

AGENTS = {
    "main": {"name": ROOT_RUN_NAME, "model": MAIN_MODEL, "base_tokens": 3050, "subagent": False},
    "order-specialist": {"name": "order-specialist", "model": SMALL_MODEL, "base_tokens": 2100, "subagent": True},
    "product-policy-specialist": {"name": "product-policy-specialist", "model": SMALL_MODEL, "base_tokens": 1900, "subagent": True},
}
# Token counts are synthetic. A model call's input is the agent's fixed part (`base_tokens`: its prompt and tool
# schemas) plus about one token per four characters of the messages it reads; a shortened search result counts
# with the length of the full retrieved text, the length its "...<truncated, N chars>" marker states.

Q_STATUS = ("Where is my order {o}?", "Can you check the status of order {o}?", "Has order {o} shipped yet?", "Any update on order {o}?")
Q_ALL_ORDERS = ("Can you give me the status of my recent orders?", "Where are my recent orders?")
Q_NOT_FOUND = ("where is my order {typed}?", "Can you check order {typed} for me?", "status of {typed} please", "I need an update on order {typed}.")
Q_CONTENTS = ("What items are in order {o}?", "Can you remind me what I bought in order {o}?", "Which products were in order {o}?")
Q_OPENED = (
    "I opened my {p} from order {o} last week. How long do I have to return it?",
    "I've already used the {p} I bought in order {o} a few times. What is the return window?",
    "The box of my {p} (order {o}) has been opened. By when do I need to send it back?",
    "I opened and used the {p} from order {o}, and it isn't for me. How many days do I have to return it?",
)
Q_UNOPENED = (
    "My {p} from order {o} is still unopened. How long do I have to return it?",
    "The {p} from order {o} is still factory sealed. What is the return window?",
    "I never took the {p} out of its box (order {o}); it is unused and sealed. How many days do I have to return it?",
    "I'd like to return an unopened {p} from order {o}. By when do I need to send it back?",
)
A_WRONG_WINDOW = (
    "You have 30 days from delivery to return your {p}. Would you like me to start the return for order {o}?",
    "No problem: TechHub accepts returns within 30 days from delivery, so your {p} is still eligible.",
    "Your {p} can be returned within 30 days from delivery. I can open a return for order {o} whenever you are ready.",
)
A_OPENED_WINDOW = (
    "Because your {p} has been opened, our Return Policy gives you 14 days from delivery to return it. It needs to be in good working condition with all accessories included.",
    "Per our Return Policy, opened electronics can be returned within 14 days from delivery, in good working condition and with all accessories. That applies to your {p}.",
)
A_UNOPENED_WINDOW = (
    "Per our Return Policy, unopened electronics can be returned within 30 days from delivery, with the original packaging and seals intact. Your {p} qualifies.",
    "Since your {p} is unopened, our Return Policy gives you 30 days from delivery to return it, as long as the original packaging and seals are intact.",
)
Q_REFUND = (
    "I'd like a refund for the {p} in order {o}. It stopped working.",
    "Please refund the {p} from order {o}; it arrived damaged.",
    "The {p} I received in order {o} is defective. I want my money back.",
)
REFUND_REASONS = ("stopped working", "arrived damaged", "defective on arrival")
Q_REFUND_TIMING = (
    "I sent my return back last week. When will my refund arrive?",
    "How long does a refund take to show up on my credit card?",
    "My return was received. How many days until I get the money back?",
)
A_REFUND_TIMING = "Per our Return Policy, refunds are processed within 5-7 business days once we receive and inspect the return, and go back to the original payment method. Credit and debit cards take 5-7 business days to appear on your statement."
Q_REFUND_TIMING_2 = "And if I paid with PayPal?"
A_REFUND_TIMING_2 = "Per our Return Policy, PayPal refunds take 3-5 business days."
Q_COMPAT = ("Will the {b} work with my {a}?", "Is the {b} compatible with the {a}?", "Can I use the {b} with the {a}?")
# (product A, product B, block of the compatibility guide that holds the answer, the answer)
COMPATIBILITY = (
    ("TECH-LAP-001", "TECH-MON-006", "MacBook Air M2 (13-inch)", "Yes. The Dell UltraSharp has a USB-C input, so one USB-C to USB-C cable connects it to the MacBook Air M2, which supports 1 external display up to 6K at 60Hz."),
    ("TECH-LAP-001", "TECH-MON-007", "MacBook Air M2 (13-inch)", "Yes, with an adapter. The LG 24\" monitor needs a USB-C to HDMI adapter on the MacBook Air M2, or our USB-C Hub for the HDMI connection."),
    ("TECH-LAP-001", "TECH-MON-009", "MacBook Air M2 (13-inch)", "Yes. The BenQ Designer Monitor has a USB-C input, so a USB-C to USB-C cable connects it directly to the MacBook Air M2."),
    ("TECH-LAP-002", "TECH-MON-006", "MacBook Pro M3 (14-inch)", "Yes. The MacBook Pro M3 connects directly to USB-C monitors such as the Dell UltraSharp over USB-C/Thunderbolt and supports up to 2 external displays."),
    ("TECH-LAP-003", "TECH-MON-009", "Dell XPS 13", "Yes. The Dell XPS 13 supports up to 2 external 4K displays; use a DisplayPort or USB-C connection for the best quality."),
    ("TECH-LAP-004", "TECH-MON-007", "Lenovo ThinkPad X1 Carbon", "Yes. The ThinkPad X1 Carbon has a built-in HDMI port that connects directly to monitors, so no adapter is needed."),
    ("TECH-LAP-005", "TECH-MON-006", "HP Pavilion 15", "Yes. The HP Pavilion 15 has a built-in HDMI port for a direct monitor connection and supports 1 external 4K display via HDMI."),
    ("TECH-LAP-001", "TECH-KEY-011", "Cross-Platform Keyboards", "Yes. The Logitech MX Keys is designed for multi-platform use and switches between Mac, Windows and iPad with the correct key mappings for each."),
    ("TECH-LAP-003", "TECH-KEY-010", "Mac-Only Peripherals", "Not recommended. The Apple Magic Keyboard technically works on Windows via Bluetooth but loses most of its functionality."),
)
SPEC_LABELS = ("Battery Life", "Weight", "Dimensions", "Display", "Storage", "Memory", "Processor", "Charging")
Q_SPEC = ("What is the {label} of the {p}?", "Can you tell me the {label} for the {p}?", "What does the product page say about the {label} of the {p}?")
Q_SPEC_2 = "And the {label}?"
Q_OTHER_CUSTOMER = (
    "Can you tell me the status of order {o}? It belongs to a colleague.",
    "What is the tracking number for order {o}? My neighbour asked me to check.",
    "Look up order {o} for me, it's my brother's order.",
)
A_OTHER_CUSTOMER = "I can't share details of order {o} because it is not on your account. If it is your order, please sign in with the account that placed it and I'll be glad to help."
Q_UNRELATED = (
    "Can you write a Python function that reverses a string?",
    "What is the capital of Australia?",
    "Give me a recipe for banana bread.",
    "Which is the tallest mountain in Europe?",
    "Can you help me write a cover letter for a job application?",
    "Explain how a binary search works.",
    "What should I watch on TV tonight?",
)
Q_UNRELATED_EMAIL = "Can you draft a short thank-you note and send it to {email} for me?"
A_UNRELATED = (
    "I can only help with TechHub orders, products and policies, so I can't help with that. Is there anything about your TechHub account I can do for you?",
    "That is outside what I can help with here. I'm TechHub's support agent, so I can look into orders, products and store policies for you.",
)
Q_THANKS = ("Thanks, that's all I needed.", "Great, thank you!", "Perfect, thanks for the help.", "OK, thank you.")
A_THANKS = ("You're welcome! Is there anything else I can help you with?", "Happy to help. Have a great day!")
Q_REPEAT = ("Thanks. Can you repeat the order number for my records?", "Which order number was that again?")
A_REPEAT = "Of course. The order number is {o}."
Q_FOLLOW_ITEMS = ("And what items are in that order?", "Which products are in it?")
Q_FOLLOW_STATUS = ("And has it shipped?", "What is its current status?")


# ---------------------------------------------------------------------------------------------
# Messages and runs
# ---------------------------------------------------------------------------------------------


def _human(text: str) -> dict:
    return {"type": "human", "content": text}


def _ai(name: str, content: str, tool_calls: list | None = None) -> dict:
    return {"type": "ai", "name": name, "content": content, "tool_calls": list(tool_calls or [])}


def _tool_message(name: str, content: str, call_id: str, status: str = "success") -> dict:
    return {"type": "tool", "name": name, "content": content, "tool_call_id": call_id, "status": status}


_LC_CLASS = {"system": "SystemMessage", "human": "HumanMessage", "ai": "AIMessage", "tool": "ToolMessage"}


def _constructor(message: dict) -> dict:
    """A message in LangChain's serialized constructor format, which is what an LLM run's inputs hold."""
    kwargs = dict(message)
    if message["type"] != "system":  # system prompts are already short, and incident A lives in one
        kwargs["content"] = _clip(kwargs["content"], 160)
    return {"lc": 1, "type": "constructor", "id": ["langchain", "schema", "messages", _LC_CLASS[message["type"]]], "kwargs": kwargs}


def _state_view(messages: list[dict]) -> list[dict]:
    """The message list as a `model` node records it, with long tool results shortened."""
    return [({**m, "content": _clip(m["content"], 160)} if len(m.get("content") or "") > 160 else m) for m in messages]


class _TraceBuilder:
    """Builds the runs of one trace. Every run gets its own millisecond so order is unambiguous."""

    def __init__(self, rng: _Rng, start: datetime, base_metadata: dict, tags: list[str], customer_id: str, planted: bool):
        self.rng, self.clock, self.base, self.tags = rng, start, base_metadata, tags
        self.customer_id, self.planted = customer_id, planted
        self.runs: list[dict] = []
        self.result_tokens: dict[str, int] = {}  # tool_call_id -> characters of the full, unshortened tool result

    def call_id(self) -> str:
        return "call_" + self.rng.hex(10)

    def spend(self, seconds: float) -> None:
        self.clock += timedelta(milliseconds=round(seconds * 1000))

    def open(self, name: str, run_type: str, parent: dict | None, inputs: dict, agent: dict, node: str | None = None, extra: dict | None = None) -> dict:
        metadata = {**self.base, "lc_agent_name": agent["name"]}
        if agent["subagent"]:
            metadata["ls_agent_type"] = "subagent"
        if node:
            metadata["langgraph_node"] = node
        run_id = _uuid7(self.clock, self.rng)
        run = {
            "id": run_id,
            "trace_id": parent["trace_id"] if parent else run_id,
            "parent_run_id": parent["id"] if parent else None,
            "dotted_order": "",
            "name": name,
            "run_type": run_type,
            "start_time": _iso(self.clock),
            "end_time": None,
            "inputs": inputs,
            "outputs": None,
            "error": None,
            "extra": {"metadata": metadata, **(extra or {})},
            "tags": list(self.tags),
        }
        self.runs.append(run)
        self.spend(0.001)
        return run

    def close(self, run: dict, outputs: dict | None, error: str | None = None) -> None:
        run["end_time"] = _iso(self.clock)
        run["outputs"] = outputs if error is None else {}  # a failed run has empty outputs
        run["error"] = error
        self.spend(0.001)

    def _tokens(self, message: dict) -> int:
        if message["type"] == "tool" and message["tool_call_id"] in self.result_tokens:
            return self.result_tokens[message["tool_call_id"]] // 4 + 6
        size = len(message.get("content") or "") + sum(len(json.dumps(c["args"])) + 20 for c in message.get("tool_calls") or [])
        return size // 4 + 6

    def model_turn(self, parent: dict, agent_key: str, state: list[dict], reply: dict) -> None:
        """One `model` node with its LLM run: the model reads `state` and returns `reply`."""
        agent = AGENTS[agent_key]
        system = {"main": MAIN_SYSTEM, "order-specialist": ORDER_SYSTEM, "product-policy-specialist": POLICY_SYSTEM}[agent_key].format(customer_id=self.customer_id)
        if agent_key == "product-policy-specialist" and self.planted:
            system += " " + PLANTED_INSTRUCTION
        input_tokens = agent["base_tokens"] + sum(self._tokens(m) for m in state)
        output_tokens = self._tokens(reply) + 4
        # A live upload also carries input_token_details and output_token_details (all zero here); left out for size.
        usage = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}
        token_usage = {"prompt_tokens": input_tokens, "completion_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}
        finish = "tool_calls" if reply["tool_calls"] else "stop"
        model = agent["model"]
        node = self.open("model", "chain", parent, {"messages": _state_view(state)}, agent, node="model")
        llm_metadata = {"ls_provider": "openai", "ls_model_name": model, "ls_model_type": "chat", "usage_metadata": usage}
        llm = self.open(
            LLM_RUN_NAME,
            "llm",
            node,
            {"messages": [[_constructor({"type": "system", "content": system})] + [_constructor(m) for m in state]]},
            agent,
            node="model",
            extra={"invocation_params": {"model": model, "model_name": model, "stream": False, "_type": "openai-chat", "stop": None}},
        )
        llm["extra"]["metadata"].update(llm_metadata)
        seconds = self.rng.uniform(1.1, 2.2) if agent_key == "main" else self.rng.uniform(0.5, 1.1)
        self.spend(seconds + output_tokens * 0.004)
        kwargs = {
            "content": reply["content"],
            "type": "ai",
            "tool_calls": reply["tool_calls"],
            "usage_metadata": usage,
            "response_metadata": {"token_usage": token_usage, "model_provider": "openai", "model_name": model, "finish_reason": finish},
        }
        generation = {
            "text": reply["content"],
            "generation_info": {"finish_reason": finish},
            "type": "ChatGeneration",
            "message": {"lc": 1, "type": "constructor", "id": ["langchain", "schema", "messages", "AIMessage"], "kwargs": kwargs},
        }
        self.close(llm, {"generations": [[generation]], "llm_output": {"token_usage": token_usage, "model_provider": "openai", "model_name": model}, "run": None, "type": "LLMResult"})
        self.close(node, {"messages": [reply]})

    def specialist(self, task_run: dict, step: dict) -> tuple[str | None, str | None]:
        """The subagent under a `task` run. Returns (final answer, None) or (None, error text)."""
        key = step["specialist"]
        agent = AGENTS[key]
        asked = _human(step["description"])
        spec = self.open(key, "chain", task_run, {"files": {}, "messages": [asked]}, agent)
        state = [asked]
        for tool_call in step["tool_calls"]:
            call = {"name": tool_call["name"], "args": tool_call["args"], "id": self.call_id(), "type": "tool_call"}
            wants = _ai(agent["name"], "", [call])
            self.model_turn(spec, key, state, wants)
            state.append(wants)
            tools = self.open("tools", "chain", spec, {"input": [call]}, agent, node="tools")
            if tool_call.get("refused"):
                # The customer-scope guard answers instead of the tool: no tool run exists, and nothing errors.
                refusal = _tool_message(call["name"], tool_call["result"], call["id"], status="error")
                self.spend(0.004)
                self.close(tools, {"messages": [refusal]})
                state.append(refusal)
                continue
            tool = self.open(call["name"], "tool", tools, call["args"], agent, node="tools", extra={"tool_call_id": call["id"]})
            self.spend(tool_call["seconds"])
            if tool_call.get("error"):
                for failed in (tool, tools, spec):
                    self.close(failed, None, tool_call["error"])
                return None, tool_call["error"]
            result = _tool_message(call["name"], tool_call["result"], call["id"])
            if tool_call.get("full_chars"):
                self.result_tokens[call["id"]] = tool_call["full_chars"]
            self.close(tool, {"output": result})
            self.close(tools, {"messages": [result]})
            state.append(result)
        final = _ai(agent["name"], step["answer"])
        self.model_turn(spec, key, state, final)
        state.append(final)
        self.close(spec, {"messages": state, "files": {}})
        return step["answer"], None

    def turn(self, turn: dict, prior: list[dict]) -> list[dict] | None:
        """One customer turn as one trace. Returns the conversation after it, or None if it failed."""
        main = AGENTS["main"]
        seen = turn.get("question_seen", turn["question"])  # what the model and the saved conversation see
        root = self.open(ROOT_RUN_NAME, "chain", None, {"messages": [{"role": "user", "content": turn["question"]}]}, main)
        state = list(prior) + [_human(seen)]
        for step in turn["steps"]:
            if step["kind"] == "interrupt":
                # request_refund pauses for human approval: the turn ends on the tool call, with no error.
                call = {"name": step["tool"], "args": step["args"], "id": self.call_id(), "type": "tool_call"}
                wants = _ai(ROOT_RUN_NAME, "", [call])
                self.model_turn(root, "main", state, wants)
                state.append(wants)
                self.close(root, {"messages": state, "files": {}})
                return state
            call = {"name": "task", "args": {"description": step["description"], "subagent_type": step["specialist"]}, "id": self.call_id(), "type": "tool_call"}
            wants = _ai(ROOT_RUN_NAME, "", [call])
            self.model_turn(root, "main", state, wants)
            state.append(wants)
            tools = self.open("tools", "chain", root, {"input": [call]}, main, node="tools")
            task = self.open("task", "tool", tools, call["args"], main, node="tools", extra={"tool_call_id": call["id"]})
            answer, error = self.specialist(task, step)
            if error:
                for failed in (task, tools, root):
                    self.close(failed, None, error)
                return None
            handed_back = _tool_message("task", answer, call["id"])
            command = {"graph": None, "update": {"messages": [handed_back]}, "resume": None, "goto": []}
            self.close(task, {"output": command})
            self.close(tools, {"output": [command]})
            state.append(handed_back)
        final = _ai(ROOT_RUN_NAME, turn["reply"])
        self.model_turn(root, "main", state, final)
        state.append(final)
        self.close(root, {"messages": state, "files": {}})
        return state


def rebuild_dotted_order(runs: list[dict]) -> list[dict]:
    """Set `dotted_order` on every run, parents before children (breadth first). Returns `runs`.

    A segment is the run's start time as `YYYYMMDDTHHMMSSffffffZ` followed by its id; a child's value
    is its parent's value, a dot, and its own segment. Batch ingest requires this field.
    """
    by_id = {r["id"]: r for r in runs}
    children: dict[str | None, list[dict]] = {}
    for run in runs:
        children.setdefault(run["parent_run_id"] if run["parent_run_id"] in by_id else None, []).append(run)
    queue = list(children.get(None, []))
    while queue:
        run = queue.pop(0)
        segment = _parse(run["start_time"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + run["id"]
        parent = by_id.get(run["parent_run_id"])
        run["dotted_order"] = f"{parent['dotted_order']}.{segment}" if parent else segment
        queue.extend(children.get(run["id"], []))
    return runs


# ---------------------------------------------------------------------------------------------
# The plan: which conversations exist, before any timestamp
# ---------------------------------------------------------------------------------------------


def _delegate(specialist: str, description: str, tool_calls: list[dict], answer: str | None) -> dict:
    return {"kind": "delegate", "specialist": specialist, "description": description, "tool_calls": tool_calls, "answer": answer}


def _db_call(rng: _Rng, name: str, args: dict, result: str | None, error: str | None = None) -> dict:
    return {"name": name, "args": args, "result": result, "error": error, "seconds": 5.0 if error else rng.uniform(0.02, 0.06)}


def _search_call(rng: _Rng, name: str, query: str, result: str | None, error: str | None = None) -> dict:
    """A document search. The stored result is shortened to 420 characters; its tokens count the full text."""
    return {"name": name, "args": {"query": query}, "result": result and _clip(result, 420), "error": error and error.format(tool=name),
            "seconds": 10.0 if error else rng.uniform(0.25, 0.55), "full_chars": len(result or "")}


def _typed_wrong(rng: _Rng, order_id: str) -> str:
    """An order id as a hurried customer types it: lower case, without dashes, or both."""
    return rng.choice((order_id.lower(), order_id.replace("-", ""), order_id.lower().replace("-", "")))


def _status_reply(order: dict) -> str:
    oid = order["id"]
    if order["status"] == "Delivered":
        return f"Order {oid} is marked Delivered. It shipped on {order['shipped']} with tracking number {order['tracking']}."
    if order["status"] == "Shipped":
        return f"Order {oid} has shipped ({order['shipped']}). The tracking number is {order['tracking']}."
    if order["status"] == "Processing":
        return f"Order {oid} is still Processing and has not shipped yet. It was placed on {order['date']}."
    return f"Order {oid} was Cancelled. It was placed on {order['date']}."


def _items_reply(order: dict) -> str:
    listed = ", ".join(f"{i['quantity']} x {i['product_id']}" for i in order["items"])
    return f"Order {order['id']} contains: {listed}."


def _plan(rng: _Rng, src: dict) -> list[dict]:
    """Every conversation with its topic, version, customer, turns, score and incident. No times yet."""
    convs: list[dict] = []
    for topic, (old, new, _, _) in TOPICS.items():
        for version, count in ((OLD_VERSION, old), (NEW_VERSION, new)):
            convs += [{"topic": topic, "version": version, "n": i, "flags": {}, "score": "unset", "incident": None, "details": {}} for i in range(count)]

    def of(topic: str, version: str) -> list[dict]:
        return [c for c in convs if c["topic"] == topic and c["version"] == version]

    # --- Incident flags (fixed positions inside each topic, so counts hold by construction) ---
    for version in (OLD_VERSION, NEW_VERSION):
        returns = of("return_window", version)
        for i, conv in enumerate(returns):
            opened = i < OPENED_BY_VERSION[version]
            conv["flags"].update(opened=opened, wrong=opened and version == NEW_VERSION)
            conv["details"]["item_condition"] = "opened" if opened else "unopened"
            if conv["flags"]["wrong"]:
                conv["incident"] = "A"
    for conv in of("where_is_my_order", NEW_VERSION)[:BURST_ERRORS]:
        conv["flags"]["error"], conv["incident"] = "burst", "B"
    of("where_is_my_order", OLD_VERSION)[0]["flags"]["error"] = "pair_a"
    of("order_contents", OLD_VERSION)[0]["flags"]["error"] = "pair_b"
    of("refund_approval", OLD_VERSION)[0]["flags"]["error"] = "single_1"
    of("spec_lookup", OLD_VERSION)[0]["flags"]["error"] = "single_2"
    of("compatibility", NEW_VERSION)[0]["flags"]["error"] = "single_3"
    for conv in convs:
        if conv["topic"] == "order_not_found":
            conv["incident"] = "C"
        if conv["topic"] == "compatibility":
            conv["incident"] = "D"
    email_conv = of("unrelated", OLD_VERSION)[0]
    email_conv["flags"]["email"], email_conv["incident"] = True, "E"

    # --- Second turns ---
    for topic, per_version in TWO_TURN.items():
        for version, (delegated, direct) in zip((OLD_VERSION, NEW_VERSION), per_version):
            free = [c for c in of(topic, version) if not c["flags"].get("error") and not c["flags"].get("email")]
            # keep the first free conversation single-turn: the timeline needs single-turn ones
            assert len(free) - 1 >= delegated + direct, (topic, version)
            for conv, kind in zip(free[1:], ["delegated"] * delegated + ["direct"] * direct):
                conv["flags"]["second"] = kind

    # --- User scores ---
    for version in (OLD_VERSION, NEW_VERSION):
        missing = of("order_not_found", version)
        for i, conv in enumerate(missing):
            conv["score"] = 0 if i < NOT_FOUND_DOWN[version] else None
    burst = [c for c in convs if c["flags"].get("error") == "burst"]
    for i, conv in enumerate(burst):
        conv["score"] = 0 if i < BURST_DOWN else None
    wrong = [c for c in convs if c["flags"].get("wrong")]
    for i, conv in enumerate(wrong):
        conv["score"] = 1 if i < WRONG_RETURN_WINDOW_SCORES["up"] else None
    for topic in ("refund_timing", "unrelated", "other_customer_data")[:OTHER_DOWN]:
        of(topic, OLD_VERSION)[-1]["score"] = 0
    unset = [c for c in convs if c["score"] == "unset"]
    no_score = SCORES["none"] - sum(1 for c in convs if c["score"] is None)
    for i, conv in enumerate(rng.shuffled(unset)):
        conv["score"] = None if i < no_score else 1

    # --- Customers. One corporate customer asks 9 compatibility questions; everyone else at most 4 things. ---
    others = [cid for cid in src["customers"] if cid != TOP_SPENDER]
    deck = [cid for _ in range(4) for cid in rng.shuffled(others)]
    top_compat = of("compatibility", OLD_VERSION)[1:7] + of("compatibility", NEW_VERSION)[1:4]
    assert len(top_compat) == TOP_SPENDER_COMPATIBILITY
    for conv in convs:
        needs_delivered = conv["topic"] in ("return_window", "refund_approval")
        if any(conv is c for c in top_compat):
            conv["customer_id"] = TOP_SPENDER
            continue
        for position, cid in enumerate(deck):
            if not needs_delivered or any(o["status"] == "Delivered" for o in src["by_customer"][cid]):
                conv["customer_id"] = deck.pop(position)
                break
        else:
            raise AssertionError("no customer left with a delivered order")

    for conv in convs:
        conv["segment"] = src["customers"][conv["customer_id"]]
        _write_turns(rng, src, conv)
    return convs


def _write_turns(rng: _Rng, src: dict, conv: dict) -> None:
    """Fill conv['turns'] from templates and real ids."""
    cid, topic, flags, details = conv["customer_id"], conv["topic"], conv["flags"], conv["details"]
    mine = src["by_customer"][cid]
    delivered = [o for o in mine if o["status"] == "Delivered"]
    products = src["products"]
    error = flags.get("error")

    def ask(specialist: str, question: str, calls: list[dict], answer: str | None) -> dict:
        return _delegate(specialist, f"Customer {cid} asks: {question}", calls, answer)

    second = None
    if topic == "where_is_my_order":
        order = rng.choice(mine)
        details["order_id"] = order["id"]
        if error == "pair_a" or (not error and conv["n"] % 6 == 5 and flags.get("second") != "delegated"):
            question = rng.choice(Q_ALL_ORDERS)
            listing = _fmt_customer_orders(mine)
            latest = sorted(mine, key=lambda o: (o["date"], o["id"]))[-1]
            reply = f"You have {len(mine)} orders on your account. The most recent is {latest['id']} ({latest['date']}), which is {latest['status']}."
            details["order_id"] = latest["id"]
            call = _db_call(rng, "get_customer_orders", {"customer_id": cid}, listing, LOCK_ERROR if error else None)
            steps = [ask("order-specialist", question, [call], reply)]
        else:
            question = rng.choice(Q_STATUS).format(o=order["id"])
            reply = _status_reply(order)
            call = _db_call(rng, "get_order_status", {"order_id": order["id"]}, _fmt_order_status(order), BURST_ERROR if error else None)
            steps = [ask("order-specialist", question, [call], reply)]
            if flags.get("second") == "delegated":
                follow = rng.choice(Q_FOLLOW_ITEMS)
                second = {"question": follow, "reply": _items_reply(order), "steps": [
                    _delegate("order-specialist", f"Customer {cid} asks about order {order['id']}: {follow}",
                              [_db_call(rng, "get_order_items", {"order_id": order["id"]}, _fmt_order_items(order))], _items_reply(order))]}
    elif topic == "order_not_found":
        order = rng.choice(mine)
        typed = _typed_wrong(rng, order["id"])
        details.update(order_id=order["id"], typed_order_id=typed)
        question = rng.choice(Q_NOT_FOUND).format(typed=typed)
        tool_text = f"Order {typed} not found."  # what tools/database.py::get_order_status returns for an unknown id
        reply = f"I could not find an order with the ID {typed}. It does not exist in our system. Please double-check the order number."
        steps = [ask("order-specialist", question, [_db_call(rng, "get_order_status", {"order_id": typed}, tool_text)], f"Order {typed} was not found.")]
    elif topic == "order_contents":
        order = rng.choice(mine)
        details["order_id"] = order["id"]
        question = rng.choice(Q_CONTENTS).format(o=order["id"])
        reply = _items_reply(order)
        call = _db_call(rng, "get_order_items", {"order_id": order["id"]}, _fmt_order_items(order), LOCK_ERROR if error else None)
        steps = [ask("order-specialist", question, [call], reply)]
        if flags.get("second") == "delegated":
            follow = rng.choice(Q_FOLLOW_STATUS)
            second = {"question": follow, "reply": _status_reply(order), "steps": [
                _delegate("order-specialist", f"Customer {cid} asks about order {order['id']}: {follow}",
                          [_db_call(rng, "get_order_status", {"order_id": order["id"]}, _fmt_order_status(order))], _status_reply(order))]}
    elif topic == "return_window":
        order = rng.choice(delivered)
        product = products[rng.choice(order["items"])["product_id"]]
        details.update(order_id=order["id"], product_id=product["id"])
        opened, wrong = flags["opened"], flags["wrong"]
        question = rng.choice(Q_OPENED if opened else Q_UNOPENED).format(p=product["name"], o=order["id"])
        if wrong:
            # Release 1.5.0: the specialist answers from its new instruction and never searches the policy.
            reply = rng.choice(A_WRONG_WINDOW).format(p=product["name"], o=order["id"])
            steps = [ask("product-policy-specialist", question, [], PLANTED_INSTRUCTION)]
        else:
            days, condition = (14, "Opened") if opened else (30, "Unopened")
            reply = rng.choice(A_OPENED_WINDOW if opened else A_UNOPENED_WINDOW).format(p=product["name"])
            found = f"Return Policy, Return Windows: {condition} Electronics can be returned within {days} days from delivery date."
            steps = [ask("product-policy-specialist", question, [_search_call(rng, "search_policy_docs", "return window for electronics", src["return_windows"])], found)]
        details["answered_window_days"] = 30 if (wrong or not opened) else 14
    elif topic == "refund_approval":
        order = rng.choice(delivered)
        item = rng.choice(order["items"])
        product = products[item["product_id"]]
        details.update(order_id=order["id"], product_id=product["id"])
        pick = rng.below(len(Q_REFUND))
        question = Q_REFUND[pick].format(p=product["name"], o=order["id"])
        price = _fmt_item_price(order, item)
        call = _db_call(rng, "get_order_item_price", {"order_id": order["id"], "product_id": product["id"]}, price, LOCK_ERROR if error else None)
        steps = [ask("order-specialist", question, [call], price)]
        if not error:
            steps.append({"kind": "interrupt", "tool": "request_refund", "args": {"order_id": order["id"], "reason": REFUND_REASONS[pick]}})
        reply = None  # the turn pauses for human approval before any reply
    elif topic == "refund_timing":
        question = rng.choice(Q_REFUND_TIMING)
        reply = A_REFUND_TIMING
        steps = [ask("product-policy-specialist", question, [_search_call(rng, "search_policy_docs", "refund processing time", src["refund_method"])],
                     "Return Policy, Refund Method: credit/debit cards take 5-7 business days to appear on the statement; PayPal 3-5 business days.")]
        if flags.get("second") == "delegated":
            second = {"question": Q_REFUND_TIMING_2, "reply": A_REFUND_TIMING_2, "steps": [
                _delegate("product-policy-specialist", f"Customer {cid} asks about refund timing: {Q_REFUND_TIMING_2}",
                          [_search_call(rng, "search_policy_docs", "refund processing time PayPal", src["refund_method"])],
                          "Return Policy, Refund Method: PayPal: 3-5 business days.")]}
    elif topic == "compatibility":
        a_id, b_id, block, answer = rng.choice(COMPATIBILITY)
        a, b = products[a_id], products[b_id]
        details.update(product_ids=[a_id, b_id])
        question = rng.choice(Q_COMPAT).format(a=a["name"], b=b["name"])
        reply = answer
        guide = _guide_block(src["guide"], block)
        page = f"[{b['name']} ({b_id})]\n## Compatibility\n\n{src['compatibility'][b_id]}"

        def lookup() -> dict:
            # The specialist reads the compatibility guide, then the product page of the second product.
            calls = [_search_call(rng, "search_policy_docs", f"{b['name']} with {a['name']}", guide),
                     _search_call(rng, "search_product_docs", f"{b['name']} compatibility", page)]
            return ask("product-policy-specialist", question, calls, answer)

        # Incident D: the main agent gets a complete answer, then delegates the same question again.
        steps = [lookup(), lookup()]
        if error:
            failing = _search_call(rng, "search_policy_docs", f"{b['name']} with {a['name']}", None, SEARCH_ERROR)
            steps = [ask("product-policy-specialist", question, [failing], None)]
    elif topic == "spec_lookup":
        candidates = [(pid, label, value) for pid, lines in src["specs"].items() for label, value in lines if label in SPEC_LABELS and "30 day" not in value]
        pid, label, value = rng.choice(candidates)
        product = products[pid]
        details.update(product_id=pid, spec=label)
        question = rng.choice(Q_SPEC).format(label=label.lower(), p=product["name"])
        shown = "\n".join(f"- **{k}:** {v}" for k, v in src["specs"][pid])
        result = f"[{product['name']} ({pid})]\n## Key Specifications\n\n{shown}"
        reply = f"According to the product documentation for the {product['name']}, the {label.lower()} is: {value}"
        call = _search_call(rng, "search_product_docs", f"{product['name']} {label.lower()}", result, SEARCH_ERROR if error else None)
        steps = [ask("product-policy-specialist", question, [call], f"{product['name']} ({pid}), Key Specifications. {label}: {value}")]
        if flags.get("second") == "delegated":
            label2, value2 = rng.choice([(k, v) for k, v in src["specs"][pid] if k in SPEC_LABELS and k != label and "30 day" not in v] or [(label, value)])
            follow = Q_SPEC_2.format(label=label2.lower())
            reply2 = f"According to the product documentation for the {product['name']}, the {label2.lower()} is: {value2}"
            second = {"question": follow, "reply": reply2, "steps": [
                _delegate("product-policy-specialist", f"Customer {cid} asks about the {product['name']}: {follow}",
                          [_search_call(rng, "search_product_docs", f"{product['name']} {label2.lower()}", result)],
                          f"{product['name']} ({pid}), Key Specifications. {label2}: {value2}")]}
    elif topic == "other_customer_data":
        foreign = rng.choice([o for o in src["orders"].values() if o["customer_id"] != cid])
        details["order_id"] = foreign["id"]
        question = rng.choice(Q_OTHER_CUSTOMER).format(o=foreign["id"])
        refusal = f"Access denied: order {foreign['id']} does not belong to this customer."
        reply = A_OTHER_CUSTOMER.format(o=foreign["id"])
        refused = {"name": "get_order_status", "args": {"order_id": foreign["id"]}, "result": refusal, "refused": True}
        steps = [ask("order-specialist", question, [refused], refusal)]
    else:  # unrelated: the main agent declines without delegating
        question = Q_UNRELATED_EMAIL.format(email=PLANTED_EMAIL) if flags.get("email") else Q_UNRELATED[conv["n"] % len(Q_UNRELATED)]
        reply = rng.choice(A_UNRELATED)
        steps = []

    first = {"question": question, "reply": reply, "steps": steps}
    if flags.get("email"):
        # PIIMiddleware redacts what the model and the saved conversation see; the root input stays raw.
        first["question_seen"] = question.replace(PLANTED_EMAIL, REDACTED_EMAIL)
    if error:
        for step in steps:
            step["answer"] = None
    conv["turns"] = [first]
    if flags.get("second") == "direct":
        if topic == "unrelated":
            other = Q_UNRELATED[(conv["n"] + 3) % len(Q_UNRELATED)]
            conv["turns"].append({"question": other, "reply": rng.choice(A_UNRELATED), "steps": []})
        elif topic in ("where_is_my_order", "order_contents") and conv["n"] % 2 == 0:
            # answered from the conversation so far, without a lookup
            conv["turns"].append({"question": rng.choice(Q_REPEAT), "reply": A_REPEAT.format(o=details["order_id"]), "steps": []})
        else:
            conv["turns"].append({"question": rng.choice(Q_THANKS), "reply": rng.choice(A_THANKS), "steps": []})
    elif second:
        conv["turns"].append(second)
    assert len(conv["turns"]) == (2 if flags.get("second") else 1), (topic, flags)


# ---------------------------------------------------------------------------------------------
# The timeline: when each root run starts
# ---------------------------------------------------------------------------------------------

_ERROR_TIMES = {  # offsets before SEED_END for the five background errors
    "single_1": timedelta(hours=16, minutes=20),
    "single_2": timedelta(hours=12, minutes=40),
    "pair_a": timedelta(hours=9, minutes=2),
    "pair_b": timedelta(hours=9, minutes=0),
    "single_3": timedelta(hours=4, minutes=10),
}


def _timeline(rng: _Rng, convs: list[dict]) -> list[tuple[datetime, dict, int]]:
    """Return (start, conversation, turn index) for all 260 root runs, oldest first.

    The errored runs have fixed times (the burst, the pair, the three singles). Every other
    conversation gets one slot of its version's part of the day; a second turn follows its first
    turn by 45 to 160 seconds. One plain order lookup is placed so that it becomes trace t-0042,
    the example the notebooks print, and one starts exactly at SEED_END as the newest trace.
    """
    scheduled: list[tuple[datetime, dict, int]] = []
    burst_offsets = iter(sorted(rng.uniform(2, BURST_WINDOW_SECONDS - 10) for _ in range(BURST_ERRORS)))
    for conv in convs:
        kind = conv["flags"].get("error")
        if kind == "burst":
            scheduled.append((SEED_END - BURST_STARTS_BEFORE_END + timedelta(seconds=round(next(burst_offsets), 3)), conv, 0))
        elif kind:
            scheduled.append((SEED_END - _ERROR_TIMES[kind], conv, 0))

    for version, block_start, block_end in ((OLD_VERSION, SEED_START, RELEASE_AT - timedelta(minutes=3)),
                                            (NEW_VERSION, RELEASE_AT + timedelta(minutes=1), SEED_END - timedelta(minutes=6))):
        ok = [c for c in convs if c["version"] == version and not c["flags"].get("error")]
        plain = [c for c in ok if c["topic"] == "where_is_my_order" and len(c["turns"]) == 1
                 and c["turns"][0]["steps"][0]["tool_calls"][0]["name"] == "get_order_status"]
        special = sorted(plain, key=lambda c: c["score"] != 1)[0]
        order = rng.shuffled(ok if version == OLD_VERSION else [c for c in ok if c is not special])
        width = (block_end - block_start) / len(order)
        jitter = [rng.uniform(0.15, 0.85) for _ in order]
        gap = [rng.uniform(45, 160) for _ in order]

        def lay_out() -> list[tuple[datetime, dict, int]]:
            block = []
            for i, conv in enumerate(order):
                start = block_start + width * (i + jitter[i])
                block.append((start, conv, 0))
                if len(conv["turns"]) == 2:
                    block.append((start + timedelta(seconds=gap[i]), conv, 1))
            return block

        if version == NEW_VERSION:
            scheduled += lay_out() + [(SEED_END, special, 0)]
            continue
        # 1.4.0: move conversations between slots until the 42nd root run of the day is the example lookup.
        for _ in range(100):
            block = lay_out()
            _, conv42, turn42 = sorted(block + scheduled, key=lambda item: item[0])[41]
            if conv42 is special:
                break
            if conv42.get("flags", {}).get("error"):
                raise AssertionError("an errored run landed on rank 42; move its fixed time")
            here = order.index(conv42)
            if len(conv42["turns"]) == 1:
                there = order.index(special)  # two one-turn conversations swap slots: no other rank changes
            else:
                there = max(i for i, c in enumerate(order) if len(c["turns"]) == 1 and c is not special)
            order[here], order[there] = order[there], order[here]
        else:
            raise AssertionError("could not place the example trace on rank 42")
        scheduled += block
    scheduled = [(start.replace(microsecond=start.microsecond // 1000 * 1000), conv, turn) for start, conv, turn in scheduled]
    scheduled.sort(key=lambda item: item[0])
    return scheduled


# ---------------------------------------------------------------------------------------------
# Reading a seed: small public helpers shared by the notebooks, the checker and the tests
# ---------------------------------------------------------------------------------------------


def root_runs(seed_or_runs) -> list[dict]:
    """The root runs (one per trace), oldest first."""
    runs = seed_or_runs["runs"] if isinstance(seed_or_runs, dict) else seed_or_runs
    return sorted((r for r in runs if r["parent_run_id"] is None), key=lambda r: r["start_time"])


def trace_key(run: dict) -> str:
    """The stable key of a run's trace, such as `t-0042` (run ids change on every upload)."""
    return run["extra"]["metadata"]["seed_trace_key"]


def trace_runs(seed_or_runs, key: str) -> list[dict]:
    """All runs of one trace, in start order. `key` is a trace key or the id of any run in the trace."""
    runs = seed_or_runs["runs"] if isinstance(seed_or_runs, dict) else seed_or_runs
    if not re.fullmatch(r"[a-z]{1,2}-\d+", key):
        key = next((trace_key(r) for r in runs if r["id"] == key or r["trace_id"] == key), key)
    return sorted((r for r in runs if trace_key(r) == key), key=lambda r: r["start_time"])


def runs_by_trace(seed_or_runs) -> dict[str, list[dict]]:
    """Trace key -> the runs of that trace."""
    runs = seed_or_runs["runs"] if isinstance(seed_or_runs, dict) else seed_or_runs
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        grouped.setdefault(trace_key(run), []).append(run)
    return grouped


def question_text(run: dict) -> str:
    """The customer's message of a root run: the content of the last message in its inputs."""
    messages = (run.get("inputs") or {}).get("messages") or []
    return str(messages[-1].get("content") or "") if messages else ""


def reply_text(run: dict) -> str:
    """The agent's reply of a root run: the content of the last message in its outputs ('' if there is none)."""
    messages = (run.get("outputs") or {}).get("messages") or []
    if not messages or messages[-1].get("type", messages[-1].get("role")) not in ("ai", "assistant"):
        return ""
    return str(messages[-1].get("content") or "")


def user_scores(seed: dict) -> dict[str, int]:
    """Trace key of a conversation's last root run -> its `user_score` (1 or 0)."""
    return {f["trace_key"]: f["score"] for f in seed["feedback"] if f["key"] == "user_score"}


_SAYS_OPENED = re.compile(r"\b(opened|used)\b", re.IGNORECASE)


def _is_wrong_return_window(run: dict) -> bool:
    """The reference rule behind the answer key: the customer says opened or used, the reply says 30 days.

    Private on purpose. The function learners write, and the one shipped for LangSmith, is
    `evaluators/online_evaluators.py::perform_eval`; a unit test checks that the two agree on the seed.
    """
    return bool(_SAYS_OPENED.search(question_text(run))) and "30 days" in reply_text(run)


def _says_30_days(run: dict) -> bool:
    return "30 days" in reply_text(run)


def sample_runs(runs: list[dict], rate: float, seed: int) -> list[dict]:
    """A reproducible fixed-size sample: `round(rate * len(runs))` runs, chosen by `random.Random(seed)`.

    A calculation on seed data, not the product: LangSmith decides per run whether to evaluate it, so
    a real 25% sampling rate scores about a quarter of the runs, not exactly a quarter. The fixed size
    gives the exercise one answer. Runs are ordered by trace key first, so the draw does not depend on
    run ids or timestamps (both change when the seed is shifted or uploaded).
    """
    ordered = sorted(runs, key=trace_key)
    generator = random.Random(seed)
    drawn = sorted((generator.random(), i) for i in range(len(ordered)))
    return [ordered[i] for i in sorted(i for _, i in drawn[: round(rate * len(ordered))])]


def _find_sampling_seed(roots: list[dict], wrong_keys: set[str]) -> int:
    """Maintainer helper: the smallest seed for which the 25% draw catches exactly SAMPLED_CAUGHT of the wrong answers."""
    return next(s for s in range(1, 10_000) if sum(trace_key(r) in wrong_keys for r in sample_runs(roots, SAMPLING_RATE, s)) == SAMPLED_CAUGHT)


def run_cost(run: dict, prices: dict | None = None) -> float:
    """Cost in US dollars of one LLM run at the given prices per 1 million tokens (0.0 for other runs)."""
    if run["run_type"] != "llm":
        return 0.0
    metadata = run["extra"]["metadata"]
    price = (prices or ILLUSTRATIVE_PRICES_PER_1M)[metadata["ls_model_name"]]
    usage = metadata["usage_metadata"]
    return (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1_000_000


def trace_costs(seed_or_runs, prices: dict | None = None) -> dict[str, float]:
    """Trace key -> summed cost of its LLM runs at the illustrative prices."""
    return {key: sum(run_cost(r, prices) for r in runs) for key, runs in runs_by_trace(seed_or_runs).items()}


def _duration(run: dict) -> float:
    return (_parse(run["end_time"]) - _parse(run["start_time"])).total_seconds()


def _failing_tool(runs: list[dict]) -> str | None:
    return next((r["name"] for r in runs if r["run_type"] == "tool" and r["error"] and r["name"] != "task"), None)


def _error_picture(seed: dict) -> dict:
    """Split the errored root runs into the densest 3-minute burst and the background."""
    failed = [r for r in root_runs(seed) if r["error"]]
    times = [_parse(r["start_time"]) for r in failed]

    def densest(points: list[datetime], seconds: int) -> tuple[int, int]:
        best = (0, 0)
        for i, start in enumerate(points):
            count = sum(1 for t in points[i:] if (t - start).total_seconds() <= seconds)
            best = max(best, (count, -i))
        return best[0], -best[1]

    count, first = densest(times, BURST_WINDOW_SECONDS)
    burst = failed[first : first + count]
    background = failed[:first] + failed[first + count :]
    background_max = densest([_parse(r["start_time"]) for r in background], ALERT_WINDOW_SECONDS)[0]
    grouped = runs_by_trace(seed)
    return {
        "failed": failed,
        "burst": burst,
        "background": background,
        "background_max": background_max,
        "burst_span_seconds": (times[first + count - 1] - times[first]).total_seconds(),
        "burst_tools": sorted({_failing_tool(grouped[trace_key(r)]) for r in burst}),
    }


# ---------------------------------------------------------------------------------------------
# generate_seed
# ---------------------------------------------------------------------------------------------


def generate_seed(rng_seed: int = RNG_SEED) -> dict:
    """Build the whole data set from nothing but the TechHub database, the documents and `rng_seed`.

    Returns a dictionary with the seed itself (`meta`, `runs`, `feedback`) and everything derived from
    it: `labels` (ground truth per conversation), `followups` (two sets of 10 traces for Section 3),
    `insights_report` and `engine_issues` (the two sample fixtures, rewritten from the seed), `answers`
    and `answer_hashes`. Every design constant is asserted before it returns.
    """
    rng = _Rng(rng_seed)
    src = _load_source()
    convs = _plan(rng, src)
    schedule = _timeline(rng, convs)

    # Thread ids follow the order in which conversations start; trace keys follow root-run order.
    thread_number = 0
    for _, conv, turn_index in schedule:
        if turn_index == 0:
            thread_number += 1
            conv["thread_id"] = f"thread-m7-{thread_number:04d}"
            conv["trace_keys"], conv["state"], conv["roots"] = [], [], []
    runs: list[dict] = []
    for number, (start, conv, turn_index) in enumerate(schedule, start=1):
        key = f"t-{number:04d}"
        builder = _TraceBuilder(rng, start, _base_metadata(conv, key), [SEED_TAG], conv["customer_id"], conv["version"] == NEW_VERSION)
        state = builder.turn(conv["turns"][turn_index], conv["state"])
        conv["state"] = state or []
        conv["trace_keys"].append(key)
        conv["roots"].append(builder.runs[0])
        runs += builder.runs
    rebuild_dotted_order(runs)

    feedback = []
    for conv in sorted(convs, key=lambda c: c["thread_id"]):
        if conv["score"] is None:
            continue
        last = conv["roots"][-1]
        feedback.append({
            "key": "user_score",
            "score": conv["score"],
            "trace_key": conv["trace_keys"][-1],
            "run_id": last["id"],
            "trace_id": last["trace_id"],
            "thread_id": conv["thread_id"],
            "run_start_time": last["start_time"],
            "created_at": _iso(_parse(last["end_time"]) + timedelta(seconds=round(rng.uniform(20, 90)))),
        })

    seed = {"meta": _meta(rng_seed, runs), "runs": runs, "feedback": feedback}
    costs = trace_costs(seed)
    by_key = runs_by_trace(seed)
    labels = {
        "_about": "Ground truth for the Module 7 seed: the topic of every conversation and the incident it belongs to. "
                  "A real project has no such labels, which is why Insights exists. This file is never uploaded to LangSmith. "
                  "cost_usd uses the illustrative prices in the seed's meta; latency_s is the agent time summed over the conversation's turns.",
        "categories": {category: [sub for _, _, sub, cat in TOPICS.values() if cat == category] for category in CATEGORY_ORDER},
        "conversations": [],
    }
    for conv in sorted(convs, key=lambda c: c["thread_id"]):
        topic = conv["topic"]
        labels["conversations"].append({
            "thread_id": conv["thread_id"],
            "trace_keys": conv["trace_keys"],
            "topic": topic,
            "subcategory": TOPICS[topic][2],
            "category": TOPICS[topic][3],
            "app_version": conv["version"],
            "customer_id": conv["customer_id"],
            "incident": conv["incident"],
            "errored": any(r["error"] for r in conv["roots"]),
            "user_score": conv["score"],
            "cost_usd": round(sum(costs[k] for k in conv["trace_keys"]), 6),
            "latency_s": round(sum(_duration(by_key[k][0]) for k in conv["trace_keys"]), 3),
            "details": conv["details"],
        })

    generated = dict(seed)
    generated["labels"] = labels
    generated["followups"] = _followups(rng, src)
    generated["insights_report"] = _insights_report(seed, labels)
    generated["engine_issues"] = _engine_issues(seed, labels, generated["insights_report"])
    generated["answers"] = answer_key(generated)
    generated["answer_hashes"] = answer_hashes(generated["answers"])
    _assert_design_constants(generated, src)
    return generated


def _base_metadata(conv: dict, key: str) -> dict:
    return {
        "thread_id": conv["thread_id"],
        "customer_id": conv["customer_id"],
        "customer_segment": conv["segment"],
        "app_version": conv["version"],
        "environment": ENVIRONMENT,
        "revision_id": REVISIONS[conv["version"]],
        "seed_trace_key": key,
        "synthetic": True,
    }


def _meta(rng_seed: int, runs: list[dict]) -> dict:
    roots = root_runs(runs)
    return {
        "about": "Synthetic production traffic for Module 7 (Monitoring, Governance & Self-Improvement). Generated by "
                 "utils/trace_seeding.py, never recorded from a real system. Every run has the tag seed:m7 and the metadata synthetic: true.",
        "format_version": 1,
        "rng_seed": rng_seed,
        "synthetic": True,
        "root_run_name": ROOT_RUN_NAME,
        "default_project": DEFAULT_PROJECT,
        "tag": SEED_TAG,
        "layout": "traces[].runs[] hold the runs; traces[].metadata, traces[].tags and traces[].trace_id apply to every run of that trace. "
                  "utils.trace_seeding.load_seed() returns a flat list of complete runs.",
        "counts": {"conversations": len({r["extra"]["metadata"]["thread_id"] for r in roots}), "traces": len(roots), "runs": len(runs)},
        "versions": {v: {"revision_id": REVISIONS[v], "note": "invented commit id"} for v in (OLD_VERSION, NEW_VERSION)},
        "clock": {"oldest_root_start": roots[0]["start_time"], "newest_root_start": roots[-1]["start_time"], "release_1_5_0_at": _iso(RELEASE_AT), "shifted_by_seconds": 0.0},
        "sampling": {"rate": SAMPLING_RATE, "seed": SAMPLING_SEED},
        "illustrative_prices_per_1m_tokens_usd": ILLUSTRATIVE_PRICES_PER_1M,
        "prices_note": "Illustrative round numbers for the lab's cost arithmetic. Not a provider's price list.",
    }


def _followups(rng: _Rng, src: dict) -> dict:
    """Two sets of 10 return-window traces dated just after the seed: release 1.5.0 again, then the fixed 1.5.1."""
    customers = [cid for cid in rng.shuffled(sorted(src["customers"])) if any(o["status"] == "Delivered" for o in src["by_customer"][cid])][:10]
    cases = []
    for i, cid in enumerate(customers):
        order = rng.choice([o for o in src["by_customer"][cid] if o["status"] == "Delivered"])
        product = src["products"][rng.choice(order["items"])["product_id"]]
        opened = i < 4
        cases.append((cid, order, product, opened, rng.choice(Q_OPENED if opened else Q_UNOPENED).format(p=product["name"], o=order["id"])))
    sets = {}
    for label, version, offset in (("before_fix", NEW_VERSION, 10), ("after_fix", FIXED_VERSION, 130)):
        runs: list[dict] = []
        for i, (cid, order, product, opened, question) in enumerate(cases):
            wrong = opened and version == NEW_VERSION
            if wrong:
                reply, calls, found = rng.choice(A_WRONG_WINDOW).format(p=product["name"], o=order["id"]), [], PLANTED_INSTRUCTION
            else:
                days, condition = (14, "Opened") if opened else (30, "Unopened")
                reply = rng.choice(A_OPENED_WINDOW if opened else A_UNOPENED_WINDOW).format(p=product["name"])
                calls = [_search_call(rng, "search_policy_docs", "return window for electronics", src["return_windows"])]
                found = f"Return Policy, Return Windows: {condition} Electronics can be returned within {days} days from delivery date."
            key = f"{'fb' if label == 'before_fix' else 'fa'}-{i + 1:02d}"
            metadata = {
                "thread_id": f"thread-m7-{label.replace('_', '-')}-{i + 1:02d}",
                "customer_id": cid,
                "customer_segment": src["customers"][cid],
                "app_version": version,
                "environment": ENVIRONMENT,
                "revision_id": REVISIONS[version],
                "seed_trace_key": key,
                "synthetic": True,
            }
            builder = _TraceBuilder(rng, SEED_END + timedelta(seconds=offset + 10 * i), metadata, [FOLLOWUP_TAG], cid, version == NEW_VERSION)
            builder.turn({"question": question, "reply": reply, "steps": [_delegate("product-policy-specialist", f"Customer {cid} asks: {question}", calls, found)]}, [])
            runs += builder.runs
        sets[label] = {"app_version": version, "revision_id": REVISIONS[version], "runs": rebuild_dotted_order(runs)}
    return {
        "_about": "Two small sets of synthetic return-window traces for Module 7 Section 3: the same 10 questions answered by release "
                  f"{NEW_VERSION} (before the fix) and by {FIXED_VERSION} (after it). Generated by utils/trace_seeding.py; they are not part of "
                  "the seeded day and are never counted in its answers. Timestamps follow the seed's clock.",
        **sets,
    }


# ---------------------------------------------------------------------------------------------
# The two sample fixtures, rewritten from the seed (PRD section 6.5)
# ---------------------------------------------------------------------------------------------

_CATEGORY_IDS = {name: f"c1000000-0000-4000-8000-00000000000{i}" for i, name in enumerate(CATEGORY_ORDER, start=1)}
_CATEGORY_TEXT = {
    "Order status and tracking": "Customers ask where an order is, what it contains, or why it cannot be found.",
    "Returns and refunds": "Customers ask whether an item can be returned, request a refund, or ask when a refund will arrive.",
    "Product specs and compatibility": "Customers ask about product specifications or whether two products work together.",
    "Out of scope or adversarial": "Requests the support agent should decline: other customers' data, or topics unrelated to TechHub.",
}
_SUBCATEGORY_TEXT = {
    "where_is_my_order": "Status and tracking questions for an order the customer owns. A short run of these conversations ends with an order-service error.",
    "order_not_found": "The agent tells the customer the order does not exist, after an order ID typed in lower case or without dashes.",
    "order_contents": "Questions about the items in an order.",
    "return_window": "Customers ask how long they have to return an item. Several answers give 30 days for opened electronics, where the policy says 14.",
    "refund_approval": "The agent prepares a refund and pauses for human approval.",
    "refund_timing": "Questions about refund processing times by payment method.",
    "compatibility": "Whether a monitor or keyboard works with a given laptop. The agent delegates the same question to the specialist twice.",
    "spec_lookup": "Battery life, weight, display and similar facts for one product.",
    "other_customer_data": "Requests for orders that belong to a different customer. The scope guard refuses.",
    "unrelated": "Coding help, general knowledge and other topics outside TechHub support.",
}
_SUBCATEGORY_IDS: dict[str, str] = {}
for _topic, _spec in TOPICS.items():  # c2...0011, 0012, 0013, 0021, ...: category number, then position inside the category
    _position = 1 + sum(1 for other in _SUBCATEGORY_IDS if TOPICS[other][3] == _spec[3])
    _SUBCATEGORY_IDS[_topic] = f"c2000000-0000-4000-8000-0000000000{CATEGORY_ORDER.index(_spec[3]) + 1}{_position}"
_TENANT_ID = "11111111-2222-3333-4444-555555555555"  # placeholder ids, not a real workspace or project
_SESSION_ID = "66666666-7777-8888-9999-aaaaaaaaaaaa"
_ISSUE_IDS = [f"7f3c2a10-5b1e-4c7a-9d42-0a1b2c3d4e0{i}" for i in (1, 2, 3)]


def _stats(conversations: list[dict]) -> dict:
    return {
        "error_rate": _round_half_up(sum(c["errored"] for c in conversations) / len(conversations), 3),
        "latency_p50": _round_half_up(statistics.median(c["latency_s"] for c in conversations), 1),
        "cost_p50": _round_half_up(statistics.median(c["cost_usd"] for c in conversations), 4),
    }


def _percent(part: int, whole: int = N_CONVERSATIONS) -> str:
    return f"{_round_half_up(100 * part / whole, 0):.0f}%"


def _insights_report(seed: dict, labels: dict) -> dict:
    """The sample Insights report: same structure as the validated fixture, every number from the seed."""
    conversations = labels["conversations"]
    roots = {trace_key(r): r for r in root_runs(seed)}
    clusters = []
    for category in CATEGORY_ORDER:
        members = [c for c in conversations if c["category"] == category]
        clusters.append({"id": _CATEGORY_IDS[category], "parent_id": None, "parent_name": None, "level": 1, "name": category,
                         "description": _CATEGORY_TEXT[category], "num_runs": len(members), "stats": _stats(members)})
    for topic, (_, _, subcategory, category) in TOPICS.items():
        members = [c for c in conversations if c["topic"] == topic]
        clusters.append({"id": _SUBCATEGORY_IDS[topic], "parent_id": _CATEGORY_IDS[category], "parent_name": category, "level": 0, "name": subcategory,
                         "description": _SUBCATEGORY_TEXT[topic], "num_runs": len(members), "stats": _stats(members)})
    by_name = {c["name"]: c for c in clusters}
    count = {topic: by_name[spec[2]]["num_runs"] for topic, spec in TOPICS.items()}
    tracking, returns, out_of_scope = (by_name[name] for name in (CATEGORY_ORDER[0], CATEGORY_ORDER[1], CATEGORY_ORDER[3]))
    where, compat, spec = by_name[TOPICS["where_is_my_order"][2]], by_name[TOPICS["compatibility"][2]], by_name[TOPICS["spec_lookup"][2]]
    where_errors = sum(c["errored"] for c in conversations if c["topic"] == "where_is_my_order")
    ratio = compat["stats"]["cost_p50"] / spec["stats"]["cost_p50"]
    slower = compat["stats"]["latency_p50"] / spec["stats"]["latency_p50"]
    assert 1.7 <= slower <= 2.3, f"compatibility takes {slower:.2f} times as long as a spec lookup; the design says about double"
    key_points = [
        f"Order status and tracking is the largest topic ({_percent(tracking['num_runs'])} of conversations). Its subcategory 'Where is my order' has the "
        f"highest error rate in the report, {100 * where['stats']['error_rate']:.1f}% ({where_errors} of {where['num_runs']} conversations), after a short order-service outage.",
        f"Returns and refunds make up {_percent(returns['num_runs'])} of conversations. In 'Return window questions' ({count['return_window']} conversations) the agent "
        "repeatedly gives 30 days for opened electronics, which the Return Policy limits to 14 days. No error is raised in these traces: the error rate of the subcategory is 0.0%.",
        f"{count['order_not_found']} conversations ({_percent(count['order_not_found'])}) end with the agent saying an order does not exist. They follow an order ID typed in lower "
        "case or without dashes; the order lookup reports the order as not found with a success status, so this subcategory also shows an error rate of 0.0%.",
        f"Compatibility questions ({count['compatibility']} conversations) are answered correctly but cost about {_times(ratio)} as much as single-product spec lookups "
        f"(median ${compat['stats']['cost_p50']:.4f} against ${spec['stats']['cost_p50']:.4f}), because the agent delegates the same question to the product-policy-specialist twice.",
        f"{_percent(out_of_scope['num_runs'])} of conversations are out of scope: {count['other_customer_data']} ask for another customer's data, and the scope guard refused "
        f"every one of them; {count['unrelated']} are unrelated to TechHub.",
    ]

    def pick(predicate) -> dict:
        return next(c for c in conversations if predicate(c))

    wrong = pick(lambda c: c["incident"] == "A" and c["user_score"] == 1)
    missing = pick(lambda c: c["topic"] == "order_not_found" and c["user_score"] == 0)
    double = pick(lambda c: c["topic"] == "compatibility" and not c["errored"])
    refused = pick(lambda c: c["topic"] == "other_customer_data")
    highlights = []
    for rank, (conv, reason, summary) in enumerate((
        (wrong, "Clear example of the wrong return window: the customer says the product was opened or used and the agent answers that 30 days apply. "
                "The product-policy-specialist answered without a policy search.", "Customer asks how long an opened product can be returned; agent says 30 days from delivery."),
        (missing, f"The order exists. The customer typed '{missing['details'].get('typed_order_id')}', get_order_status returned 'Order "
                  f"{missing['details'].get('typed_order_id')} not found.', and the agent told the customer the order does not exist.",
         "Customer types the order ID in a different form; agent reports that no such order exists."),
        (double, "Typical double delegation: two task calls with the same question to the product-policy-specialist before the final answer.",
         "Customer asks whether two products work together; the answer is correct after two specialist calls."),
        (refused, f"Shows the scope guard working: the request names order {refused['details'].get('order_id')}, which belongs to a different customer, and is refused without a database call.",
         "Customer asks for the status of an order that belongs to someone else; agent declines."),
    ), start=1):
        key = conv["trace_keys"][0]
        highlights.append({"run_id": roots[key]["id"], "cluster_id": _SUBCATEGORY_IDS[conv["topic"]], "cluster_name": conv["subcategory"], "rank": rank,
                           "highlight_reason": reason, "summary": f"{summary} (seed trace {key})"})
    created = SEED_END + timedelta(seconds=60)
    return {
        "id": "5b0e6c1a-2d3f-4a5b-8c7d-9e0f1a2b3c4d",
        "name": "TechHub support: topics and failure modes (hand-built sample, not real Insights output)",
        "status": "success",
        "start_time": _iso_z(created + timedelta(seconds=5)),
        "end_time": _iso_z(created + timedelta(seconds=190)),
        "created_at": _iso_z(created),
        "metadata": None,
        "shape": None,
        "error": None,
        "config_id": None,
        "clusters": clusters,
        "report": {
            "title": "What TechHub customers ask, and where the support agent struggles",
            "created_at": _iso_z(created + timedelta(seconds=188)),
            "key_points": key_points,
            "highlighted_traces": highlights,
        },
    }


def _times(ratio: float) -> str:
    assert 1.8 <= ratio <= 2.2, f"compatibility costs {ratio:.2f} times a spec lookup; the design says about twice"
    return "twice"


def _engine_issues(seed: dict, labels: dict, report: dict) -> dict:
    """The sample Engine issue board: the three validated issues, with evidence taken from seeded traces."""
    conversations = labels["conversations"]
    roots = {trace_key(r): r for r in root_runs(seed)}

    def starts(predicate) -> list[datetime]:
        return sorted(_parse(roots[c["trace_keys"][0]]["start_time"]) for c in conversations if predicate(c))

    wrong = [c for c in conversations if c["incident"] == "A"]
    wrong_times, missing_times, double_times = starts(lambda c: c["incident"] == "A"), starts(lambda c: c["incident"] == "C"), starts(lambda c: c["incident"] == "D")
    highlighted = next(h["run_id"] for h in report["report"]["highlighted_traces"] if h["rank"] == 1)
    first = next(c for c in wrong if roots[c["trace_keys"][0]]["id"] == highlighted)
    second = next(c for c in wrong if c is not first and c["user_score"] is None)
    third = next(c for c in wrong if c is not first and c["user_score"] == 1)

    def evidence(conv: dict, comment: str) -> dict:
        root = roots[conv["trace_keys"][0]]
        return {"run_id": root["id"], "trace_id": root["trace_id"], "start_time": _iso_z(_parse(root["start_time"])), "comment": comment, "seed_trace_key": conv["trace_keys"][0]}

    first_root = roots[first["trace_keys"][0]]
    watching_since = SEED_END - timedelta(hours=10)
    fix_dispatched = SEED_END - timedelta(hours=3)
    issues = [
        {
            "id": _ISSUE_IDS[0], "tenant_id": _TENANT_ID, "session_id": _SESSION_ID, "type": "actionable",
            "name": "Agent quotes the 30-day return window for opened electronics",
            "description": "When a customer says the product has been opened or used, the agent still answers that it can be returned within 30 days. The return policy gives "
                           "opened electronics 14 days from delivery. In these traces the product-policy-specialist answers without calling search_policy_docs, so no tool error is "
                           f"raised and the answer looks normal. Every trace is on app_version {NEW_VERSION} (revision {REVISIONS[NEW_VERSION]}). Customers outside the 14-day window "
                           "are told they can still return the item.",
            "severity": 1, "status": "open", "tags": ["Hallucination"],
            "created_at": _iso_z(wrong_times[0] + timedelta(minutes=25)), "updated_at": _iso_z(wrong_times[-1] + timedelta(minutes=2)),
            "first_seen_at": _iso_z(wrong_times[0]), "last_seen_at": _iso_z(wrong_times[-1]),
            "proposed_fix": "In the product-policy-specialist prompt, remove the sentence that states one return window for any item, require a search_policy_docs call for every "
                            "return, refund or warranty question, and require the answer to name the product condition (unopened, opened, other) it applies to.",
            "fixes": [], "recurrences_since_watching": 0,
        },
        {
            "id": _ISSUE_IDS[1], "tenant_id": _TENANT_ID, "session_id": _SESSION_ID, "type": "actionable",
            "name": "Order lookup reports an existing order as not found",
            "description": "For order IDs typed in lower case or without dashes, get_order_status returns 'Order <id> not found.' with a success status. The order-specialist "
                           "treats that text as proof that the order does not exist and the agent tells the customer so, although the order exists under the normalised ID and "
                           "belongs to that customer.",
            "severity": 2, "status": "fixing", "tags": ["Silent tool error"],
            "created_at": _iso_z(missing_times[0] + timedelta(minutes=30)),
            "updated_at": _iso_z(max(fix_dispatched + timedelta(minutes=18), missing_times[-1] + timedelta(minutes=2))),
            "first_seen_at": _iso_z(missing_times[0]), "last_seen_at": _iso_z(missing_times[-1]),
            "proposed_fix": "Normalise order IDs to the ORD-YYYY-NNNN form before the lookup, and have get_order_status say that no order with this ID exists for this customer "
                            "instead of a bare 'not found'.",
            "fix_branch": "engine/normalise-order-ids", "fix_pr_number": 42, "fix_dispatched_at": _iso_z(fix_dispatched),
            "fixes": [{
                "id": "9c1d7e52-3a4b-4f6c-8d7e-0f1a2b3c4d5e", "branch": "engine/normalise-order-ids", "pr_number": 42, "provider": "github",
                "provider_web_base_url": "https://github.com", "repo_url": "https://github.com/example-org/techhub-support-agent",
                "created_at": _iso_z(fix_dispatched + timedelta(minutes=18)), "updated_at": _iso_z(fix_dispatched + timedelta(minutes=18)),
            }],
            "recurrences_since_watching": 0,
        },
        {
            "id": _ISSUE_IDS[2], "tenant_id": _TENANT_ID, "session_id": _SESSION_ID, "type": "finding",
            "name": "Compatibility questions take two specialist delegations where one would do",
            "description": "On product compatibility questions the main agent delegates to the product-policy-specialist, receives a complete answer, then delegates the same "
                           "question again before replying. Answers are correct; median latency and cost for these conversations are about double those of single-product spec lookups.",
            "severity": 3, "status": "watching", "tags": ["Inefficient path"],
            "created_at": _iso_z(double_times[0] + timedelta(minutes=30)), "updated_at": _iso_z(double_times[-1] + timedelta(minutes=2)),
            "first_seen_at": _iso_z(double_times[0]), "last_seen_at": _iso_z(double_times[-1]),
            "watching_since": _iso_z(watching_since), "fixes": [],
            "recurrences_since_watching": sum(1 for t in double_times if t > watching_since),
        },
    ]
    return {
        "_fixture": {
            "what": "Hand-built sample of a LangSmith Engine issue board for the TechHub support agent. NOT real Engine output. Generated from the Module 7 seed by "
                    "utils/trace_seeding.py, so every trace it cites is a seeded trace.",
            "shape_of_issues": "Each item in `issues` uses only keys from the REST schema `issues.Issue` (GET /api/v1/platform/issues, which returns a bare JSON array of these objects).",
            "shape_of_evidence": "Items use the documented webhook `data.trace` shape (run_id, trace_id, start_time, comment) plus `seed_trace_key`, which is this module's own key "
                                 "for finding the trace in the seed. The shape of the API's own `traces` field is undocumented, so it is not used here.",
            "shape_of_offline_examples": "Items mirror the request body of `langsmith projects issues examples propose` (run_id, assertions[{key, comment}]). The shape of the API's "
                                         "own `proposed_examples` field is undocumented, so it is not used here.",
            "clock": "All timestamps are on the seed's clock. `utils.trace_seeding.load_engine_issues(seed)` shifts them together with the seed.",
            "validation": "tests/test_module7_fixtures.py loads every issue with langsmith.types.issue.Issue and checks every evidence comment against the cited seed trace. "
                          "The structure is validated; the wording, length and style of real Engine output are not.",
        },
        "issues": issues,
        "evidence": {
            _ISSUE_IDS[0]: [
                evidence(first, f"Customer: '{question_text(first_root)}' Agent: '{reply_text(first_root)}' No search_policy_docs call in the trace."),
                evidence(second, "The product-policy-specialist answered without calling search_policy_docs. The reply gives 30 days for a product the customer describes as opened or used."),
                evidence(third, "The customer gave a thumbs-up (user_score 1), so user feedback does not show this failure. The feedback cited for this trace is the online evaluator's score: wrong_return_window = 1."),
            ]
        },
        "offline_examples": {
            _ISSUE_IDS[0]: [{
                "run_id": first_root["id"],
                "seed_trace_key": first["trace_keys"][0],
                "assertions": [
                    {"key": ASSERTION_KEYS[0], "comment": "States that opened electronics can be returned within 14 days of delivery"},
                    {"key": ASSERTION_KEYS[1], "comment": "Does not tell the customer that an opened product has a 30-day return window"},
                ],
            }]
        },
    }


def next_action_for(issue: dict) -> str:
    """The triage rule of Section 3, used to compute the answer key (the learner writes their own)."""
    if issue.get("type") == "finding":
        return "save_for_later"
    if issue.get("status") == "fixing" and issue.get("fixes"):
        return "review_pull_request"
    return "apply_fix_and_add_examples"


# ---------------------------------------------------------------------------------------------
# The answer key (PRD section 6.6)
# ---------------------------------------------------------------------------------------------


def answer_key(seed: dict, labels: dict | None = None, insights_report: dict | None = None, engine_issues: dict | None = None, followups: dict | None = None) -> dict:
    """Compute every checked answer from the seed. `data/answers.json` is this dictionary, written by the generator.

    `labels`, the two fixtures and the follow-up sets are taken from the arguments, else from the seed
    dictionary (`generate_seed()` returns them), else from the files in `workshop_modules/module_7/data/`.
    The values under the keys that start with `s4_masking`, `s4_routes` and `s4_blocks` are not in the
    seed: they are measured or documented facts, written here as constants with their sources.
    """

    labels = labels or seed.get("labels") or load_labels()
    report = insights_report or seed.get("insights_report") or load_insights_report()
    board = engine_issues or seed.get("engine_issues") or load_engine_issues()
    follow = followups or seed.get("followups") or load_followups()
    roots = root_runs(seed)
    grouped = runs_by_trace(seed)
    scores = user_scores(seed)
    conversations = labels["conversations"]

    def tool_names(key: str) -> list[str]:
        return [r["name"] for r in grouped[key] if r["run_type"] == "tool"]

    def not_found_result(key: str) -> bool:
        return any(r["run_type"] == "tool" and re.fullmatch(r"Order \S+ not found\.", str(((r["outputs"] or {}).get("output") or {}).get("content", ""))) for r in grouped[key])

    wrong = [r for r in roots if _is_wrong_return_window(r)]
    wrong_keys = sorted(trace_key(r) for r in wrong)
    down = [key for key, score in scores.items() if score == 0]
    errors = _error_picture(seed)
    new_version = [r for r in roots if r["extra"]["metadata"]["app_version"] == NEW_VERSION]
    sampled = sample_runs(roots, SAMPLING_RATE, SAMPLING_SEED)

    top = [c for c in report["clusters"] if c["parent_id"] is None]
    subs = [c for c in report["clusters"] if c["parent_id"] is not None]
    largest = max(top, key=lambda c: c["num_runs"])
    worst = max(subs, key=lambda c: c["stats"]["error_rate"])
    claim = next(c for c in subs if c["name"] == TOPICS["return_window"][2])
    claim_keys = {key for c in conversations if c["subcategory"] == claim["name"] for key in c["trace_keys"]}

    evidence_key = board["evidence"][board["issues"][0]["id"]][0]["seed_trace_key"]
    correct = next(c for c in conversations if c["topic"] == "return_window" and c["app_version"] == OLD_VERSION and c["details"]["item_condition"] == "opened")
    missing_tools = sorted(set(tool_names(correct["trace_keys"][0])) - set(tool_names(evidence_key)) - {"task"})
    by_id = {r["id"]: r for r in grouped[correct["trace_keys"][0]]}
    missing_run = next(r for r in grouped[correct["trace_keys"][0]] if r["name"] == missing_tools[0])
    ancestor = by_id[missing_run["parent_run_id"]]
    while ancestor["name"] in ("tools", "model"):
        ancestor = by_id[ancestor["parent_run_id"]]

    email = re.compile(EMAIL_PATTERN)
    in_inputs = [r for r in roots if email.search(json.dumps(r["inputs"]))]
    in_outputs = [r for r in roots if email.search(json.dumps(r["outputs"]))]

    spend: dict[str, float] = {}
    for conv in conversations:
        spend[conv["customer_id"]] = spend.get(conv["customer_id"], 0.0) + conv["cost_usd"]
    span_hours = (_parse(roots[-1]["start_time"]) - _parse(roots[0]["start_time"])).total_seconds() / 3600

    # Section 4's spend-cap sketch: every model call in time order under a daily cap of half the day's spend.
    model_calls = sorted((r for r in seed["runs"] if r["run_type"] == "llm"), key=lambda r: r["end_time"])
    day_spend = sum(run_cost(r) for r in model_calls)
    daily_cap = round(day_spend / 2, 2)
    recorded, crossing = 0.0, None
    for number, run in enumerate(model_calls, start=1):
        if recorded + run_cost(run) >= daily_cap:
            crossing = number
            break
        recorded += run_cost(run)

    return {
        "_about": "Answer key of Module 7, written by utils/trace_seeding.py::answer_key from the seed. The keys s1_... to s4_... are the "
                  "checker ids of utils/monitoring_checks.py. `reference` holds numbers the notebooks print but no checker grades.",
        "s1_signals": {
            "errored_root_runs": len(errors["failed"]),
            "thumbs_down_conversations": len(down),
            "thumbs_down_after_order_not_found": sum(not_found_result(key) for key in down),
            "thumbs_down_on_wrong_return_window": sum(scores.get(key) == 0 for key in wrong_keys),
        },
        "s1_evaluator": {"flagged_trace_keys": wrong_keys},
        "s1_filter_sample": {
            "all_root_runs": {"scored": len(roots), "caught": len(wrong)},
            "app_version_1_5_0": {"scored": len(new_version), "caught": sum(_is_wrong_return_window(r) for r in new_version)},
            "sample_25_percent": {"scored": len(sampled), "caught": sum(_is_wrong_return_window(r) for r in sampled)},
        },
        "s1_alert": {
            "background_max_in_5_minutes": errors["background_max"],
            "burst_errors": len(errors["burst"]),
            "threshold": errors["background_max"] + 1,
            "failing_tool": errors["burst_tools"][0],
        },
        "s1_routing": {"selected": len(wrong)},
        "s2_report": {
            "largest_category": largest["name"],
            "largest_category_conversations": largest["num_runs"],
            "largest_category_share": _round_half_up(largest["num_runs"] / sum(c["num_runs"] for c in top), 2),
            "highest_error_rate_subcategory": worst["name"],
            "highest_error_rate": worst["stats"]["error_rate"],
        },
        "s2_claim": {
            "conversations": claim["num_runs"],
            "error_rate": claim["stats"]["error_rate"],
            "flagged": sum(trace_key(r) in claim_keys for r in wrong),
        },
        "s3_evidence": {"missing_tool": missing_tools[0], "under_run": ancestor["name"]},
        "s3_triage": {"actions": [next_action_for(issue) for issue in board["issues"]]},
        "s3_assertions": {"assertions": sorted(a["key"] for a in board["offline_examples"][board["issues"][0]["id"]][0]["assertions"])},
        "s4_leak": {"root_runs_with_raw_email": len({r["id"] for r in in_inputs + in_outputs}), "in_inputs": len(in_inputs), "in_outputs": len(in_outputs)},
        # Measured offline with the capture client (research note 06 section 4.6): the count with the middleware
        # alone depends on the installed LangChain version, so the check asserts "more than 0, then 0".
        "s4_masking": {"middleware_only_more_than_zero": True, "with_anonymizer": 0, "control_string_unchanged": True},
        # Verified offline by constructing the model without calling it (research note 06 section 1.2).
        "s4_routes": {"base_url": "https://gateway.smith.langchain.com/openai/v1"},
        # Documented block responses and the exception LangChain raises for each (research note 06 sections 2.1, 2.7);
        # the retried status is the one in agents/middleware/fault_tolerance.py::_TRANSIENT_STATUSES.
        "s4_blocks": {
            "402": {"policy_type": "spend_limit", "exception": "APIStatusError"},
            "429": {"policy_type": "rate_limit", "exception": "RateLimitError"},
            "403": {"policy_type": "model_access", "exception": "PermissionDeniedError"},
            "retried_statuses": [429],
        },
        "reference": {
            "conversations": len(conversations),
            "one_turn_conversations": sum(len(c["trace_keys"]) == 1 for c in conversations),
            "two_turn_conversations": sum(len(c["trace_keys"]) == 2 for c in conversations),
            "root_runs": len(roots),
            "runs": len(seed["runs"]),
            "span_hours": int(-(-span_hours // 1)),
            "root_runs_by_version": {v: sum(r["extra"]["metadata"]["app_version"] == v for r in roots) for v in (OLD_VERSION, NEW_VERSION)},
            "user_scores": {"up": sum(s == 1 for s in scores.values()), "down": len(down), "none": len(conversations) - len(scores)},
            "thumbs_down_by_version": {v: sum(c["user_score"] == 0 for c in conversations if c["app_version"] == v) for v in (OLD_VERSION, NEW_VERSION)},
            "thumbs_down_after_errored_run": sum(any(r["error"] for r in grouped[key]) for key in down),
            "s1_evaluator": {
                "naive_flagged": sum(_says_30_days(r) for r in roots),
                "naive_flagged_correct_answers": sum(_says_30_days(r) and not _is_wrong_return_window(r) for r in roots),
                "app_versions": sorted({r["extra"]["metadata"]["app_version"] for r in wrong}),
                "with_search_policy_docs_run": sum("search_policy_docs" in tool_names(trace_key(r)) for r in wrong),
                "user_scores": {"up": sum(scores.get(k) == 1 for k in wrong_keys), "down": sum(scores.get(k) == 0 for k in wrong_keys), "none": sum(k not in scores for k in wrong_keys)},
            },
            "s1_alert": {"burst_span_seconds": errors["burst_span_seconds"], "background_errors": len(errors["background"])},
            "s3_followup": {
                "traces_per_set": len(root_runs(follow["before_fix"]["runs"])),
                "before_fix_flagged": sum(_is_wrong_return_window(r) for r in root_runs(follow["before_fix"]["runs"])),
                "after_fix_flagged": sum(_is_wrong_return_window(r) for r in root_runs(follow["after_fix"]["runs"])),
            },
            "s4_spend": {
                "top_spender": max(sorted(spend), key=lambda cid: spend[cid]),
                "costliest_subcategory": max(subs, key=lambda c: c["stats"]["cost_p50"])["name"],
                "day_spend_usd": round(day_spend, 2),
                "daily_cap_usd": daily_cap,
                "model_calls": len(model_calls),
                "cap_crossing_call": crossing,
            },
        },
    }


def answer_hashes(answers: dict) -> dict:
    """SHA-256 of each answer's canonical JSON, whole and per field, for places where `answers.json` is removed."""
    graded = {key: value for key, value in answers.items() if re.match(r"s\d_", key)}
    return {
        "_about": "SHA-256 hashes of the Module 7 answers. `answers` hashes each checker id's whole answer; `fields` hashes each field on its own. "
                  "The text that is hashed is utils.trace_seeding.canonical_json(value): json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).",
        "algorithm": "sha256",
        "answers": {key: sha256_of(value) for key, value in graded.items()},
        "fields": {key: {field: sha256_of(item) for field, item in value.items()} for key, value in graded.items()},
    }


# ---------------------------------------------------------------------------------------------
# Assertions: every design constant, checked on what was actually built
# ---------------------------------------------------------------------------------------------


def _assert_design_constants(generated: dict, src: dict) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(f"Module 7 seed: {message}")

    runs, labels, answers = generated["runs"], generated["labels"], generated["answers"]
    conversations = labels["conversations"]
    roots = root_runs(runs)
    grouped = runs_by_trace(runs)
    reference = answers["reference"]

    # 6.2: sizes, versions, topics
    check(len(conversations) == N_CONVERSATIONS and len(roots) == N_ROOT_RUNS, "200 conversations and 260 root runs")
    check(reference["one_turn_conversations"] == N_CONVERSATIONS - N_TWO_TURN and reference["two_turn_conversations"] == N_TWO_TURN, "140 one-turn and 60 two-turn conversations")
    check(reference["root_runs_by_version"] == ROOT_RUNS_BY_VERSION, "156 and 104 root runs by version")
    check({v: sum(c["app_version"] == v for c in conversations) for v in CONVERSATIONS_BY_VERSION} == CONVERSATIONS_BY_VERSION, "120 and 80 conversations by version")
    check(3250 <= len(runs) <= 3350, f"about 3,300 runs, got {len(runs)}")
    for topic, (old, new, subcategory, category) in TOPICS.items():
        for version, expected in ((OLD_VERSION, old), (NEW_VERSION, new)):
            got = sum(c["topic"] == topic and c["app_version"] == version for c in conversations)
            check(got == expected, f"{topic} on {version}: {got} conversations, expected {expected}")
    for conv in conversations:
        versions = {grouped[key][0]["extra"]["metadata"]["app_version"] for key in conv["trace_keys"]}
        check(versions == {conv["app_version"]}, f"{conv['thread_id']} spans two versions")
    starts = [_parse(r["start_time"]) for r in roots]
    check(starts[-1] == SEED_END and starts[0] >= SEED_START, "root runs lie inside the 20-hour span and the newest starts at SEED_END")
    check(all((_parse(r["start_time"]) < RELEASE_AT) == (r["extra"]["metadata"]["app_version"] == OLD_VERSION) for r in roots), "1.4.0 before the release time, 1.5.0 after")
    check([trace_key(r) for r in roots] == [f"t-{i:04d}" for i in range(1, N_ROOT_RUNS + 1)], "trace keys follow start order")
    example = grouped["t-0042"]
    check(len(example) == 14 and not example[0]["error"] and "get_order_status" in [r["name"] for r in example], "t-0042 is a plain 14-run order lookup")
    for run in runs:
        metadata = run["extra"]["metadata"]
        check(all(key in metadata for key in CALLER_METADATA_KEYS), f"caller metadata missing on {run['name']}")
        check(SEED_TAG in run["tags"] and metadata["synthetic"] is True, "seed tag and synthetic flag on every run")
        check(run["run_type"] in ("chain", "llm", "tool"), "run types")
        inside = metadata["lc_agent_name"] != ROOT_RUN_NAME
        check(("ls_agent_type" in metadata) == inside, "ls_agent_type only inside specialists")
        if run["run_type"] == "llm":
            usage = metadata["usage_metadata"]
            message = run["outputs"]["generations"][0][0]["message"]["kwargs"]
            check(run["name"] == LLM_RUN_NAME and metadata["ls_provider"] == "openai" and metadata["ls_model_type"] == "chat", "LLM run identity")
            check(metadata["ls_model_name"] == (SMALL_MODEL if inside else MAIN_MODEL), "model by agent")
            check(message["usage_metadata"] == usage and message["response_metadata"]["token_usage"]["prompt_tokens"] == usage["input_tokens"]
                  and run["outputs"]["llm_output"]["token_usage"]["completion_tokens"] == usage["output_tokens"], "token counts in four places")
    for root in roots:
        check(root["name"] == ROOT_RUN_NAME and "messages" in root["inputs"] and len(root["inputs"]["messages"]) == 1, "root inputs hold the one new message")
        check(bool(root["error"]) != ("messages" in (root["outputs"] or {})), "root outputs hold messages unless the run failed")
    for key, members in grouped.items():
        ids = {r["id"] for r in members}
        check(sum(r["parent_run_id"] is None for r in members) == 1 and all(r["parent_run_id"] in ids for r in members if r["parent_run_id"]), f"{key} is one tree")
        check(all(r["trace_id"] == members[0]["trace_id"] for r in members), f"{key} has one trace id")
        check(all(_DOTTED_SEGMENT.match(segment) for r in members for segment in r["dotted_order"].split(".")), "dotted_order segments")
        check(len({r["start_time"] for r in members}) == len(members), f"{key} has runs that start in the same millisecond")
        check(all(r["end_time"] >= r["start_time"] for r in members), "end after start")
    shapes = sorted({len(members) for members in grouped.values()})
    # 3 direct answer; 10 answered without a tool, or failed at the first tool; 13 refused by the scope guard;
    # 14 one delegation with one tool; 33 two delegations with two searches each (incident D)
    check(set(shapes) == {3, 10, 13, 14, 33}, f"tree sizes {shapes}")
    for conv in conversations:
        if len(conv["trace_keys"]) == 2:
            first, second = (grouped[key][0] for key in conv["trace_keys"])
            check(second["start_time"] > first["end_time"], f"{conv['thread_id']}: second turn starts before the first ends")

    # 6.3 A: the wrong return window
    wrong = [r for r in roots if _is_wrong_return_window(r)]
    thirty = [r for r in roots if _says_30_days(r)]
    planted = {key for c in conversations if c["incident"] == "A" for key in c["trace_keys"]}
    check({trace_key(r) for r in wrong} == planted and len(wrong) == 11, "the reference rule flags exactly the 11 planted traces")
    check(len(thirty) == 23, f"23 replies contain '30 days', got {len(thirty)}")
    check(not any(re.search(r"30[- ]day\b|thirty days", reply_text(r), re.I) for r in roots), "no reply spells the window another way")
    check(reference["s1_evaluator"] == {"naive_flagged": 23, "naive_flagged_correct_answers": 12, "app_versions": [NEW_VERSION], "with_search_policy_docs_run": 0,
                                        "user_scores": WRONG_RETURN_WINDOW_SCORES}, "incident A reference values")
    returns = [c for c in conversations if c["topic"] == "return_window"]
    for version in (OLD_VERSION, NEW_VERSION):
        opened = [c for c in returns if c["app_version"] == version and c["details"]["item_condition"] == "opened"]
        check(len(opened) == OPENED_BY_VERSION[version], f"opened-item conversations on {version}")
        check(all(c["details"]["answered_window_days"] == (30 if version == NEW_VERSION else 14) for c in opened), "opened items: 14 days on 1.4.0, 30 on 1.5.0")
    for conv in returns:
        question = question_text(grouped[conv["trace_keys"][0]][0])
        check(bool(_SAYS_OPENED.search(question)) == (conv["details"]["item_condition"] == "opened"), f"wording of {conv['trace_keys'][0]}")
        if conv["incident"] != "A":
            check("search_policy_docs" in [r["name"] for r in grouped[conv["trace_keys"][0]]], "correct return-window answers follow a policy search")

    # 6.3 B: errors
    errors = _error_picture(generated)
    check(len(errors["failed"]) == BURST_ERRORS + BACKGROUND_ERRORS == 13, "13 errored root runs")
    check(len(errors["burst"]) == BURST_ERRORS and errors["burst_span_seconds"] <= BURST_WINDOW_SECONDS and errors["burst_tools"] == ["get_order_status"], "the burst")
    for root in errors["burst"]:
        before_end = (SEED_END - _parse(root["start_time"])).total_seconds() / 60
        check(49 <= before_end <= 52, "the burst lies 52 to 49 minutes before the newest run")
    check(errors["background_max"] == 2, "at most 2 background errors in any 5 minutes")
    background = sorted(_parse(r["start_time"]) for r in errors["background"])
    gaps = [(b - a).total_seconds() for a, b in zip(background, background[1:])]
    check(sorted(gaps)[0] == 120 and all(g > 1800 for g in sorted(gaps)[1:]), "one pair 2 minutes apart, the other background errors more than 30 minutes from any error")
    check(all(min(abs((t - _parse(b["start_time"])).total_seconds()) for b in errors["burst"]) > 1800 for t in background), "background errors are far from the burst")
    for root in errors["failed"]:
        failed = [r for r in grouped[trace_key(root)] if r["error"]]
        check(any(r["run_type"] == "tool" and r["name"] != "task" for r in failed) and all(r["outputs"] == {} for r in failed), "an errored trace has an errored tool run and empty outputs")
    check(sum(bool(r["error"]) for r in runs if r["parent_run_id"] is None) == 13 and all(c["errored"] == (c["trace_keys"][0] in {trace_key(r) for r in errors["failed"]}) for c in conversations),
          "each errored root run belongs to a different conversation")

    # 6.3 C: orders reported as not found
    not_found = [r for r in runs if r["run_type"] == "tool" and re.fullmatch(r"Order \S+ not found\.", str(((r["outputs"] or {}).get("output") or {}).get("content", "")))]
    check(len(not_found) == 19 and all(r["error"] is None and r["outputs"]["output"]["status"] == "success" and r["name"] == "get_order_status" for r in not_found), "19 'not found' results with status success")
    for conv in conversations:
        if conv["topic"] == "order_not_found":
            real, typed = conv["details"]["order_id"], conv["details"]["typed_order_id"]
            check(src["orders"][real]["customer_id"] == conv["customer_id"] and typed != real and typed.upper().replace("-", "") == real.replace("-", ""), "the order exists and belongs to the customer")

    # 6.3 D: double delegation, top spender
    for conv in conversations:
        if conv["topic"] == "compatibility" and not conv["errored"]:
            members = grouped[conv["trace_keys"][0]]
            tasks = [r for r in members if r["name"] == "task"]
            check(len(tasks) == 2 and tasks[0]["inputs"] == tasks[1]["inputs"] and tasks[0]["inputs"]["subagent_type"] == "product-policy-specialist", "two identical delegations")
    check(sum(c["topic"] == "compatibility" and c["customer_id"] == TOP_SPENDER for c in conversations) == TOP_SPENDER_COMPATIBILITY, "CUST-010 asks 9 compatibility questions")
    check(src["customers"][TOP_SPENDER] == "Corporate", "CUST-010 is a corporate customer")
    check(reference["s4_spend"] == {"top_spender": TOP_SPENDER, "costliest_subcategory": TOPICS["compatibility"][2], "day_spend_usd": DAY_SPEND_USD,
                                    "daily_cap_usd": DAILY_CAP_USD, "model_calls": MODEL_CALLS, "cap_crossing_call": CAP_CROSSING_CALL},
          "top spender, costliest subcategory and the spend-cap sketch (4.92, 2.46, call 473 of 934)")

    # 6.3 E: the email address
    email = re.compile(EMAIL_PATTERN)
    carriers = [r for r in runs if email.search(json.dumps(r["inputs"])) or email.search(json.dumps(r["outputs"]))]
    check(len(carriers) == 1 and carriers[0]["parent_run_id"] is None and PLANTED_EMAIL in carriers[0]["inputs"]["messages"][0]["content"]
          and REDACTED_EMAIL in carriers[0]["outputs"]["messages"][0]["content"], "one raw email, in one root run's inputs only")
    check(answers["s4_leak"] == {"root_runs_with_raw_email": 1, "in_inputs": 1, "in_outputs": 0}, "s4_leak")

    # 6.3 notes: refusals, scores
    for conv in conversations:
        if conv["topic"] == "other_customer_data":
            members = grouped[conv["trace_keys"][0]]
            check(not any(r["error"] for r in members) and not any(r["run_type"] == "tool" and r["name"] != "task" for r in members)
                  and any("Access denied: order" in json.dumps(r["outputs"]) for r in members if r["name"] == "tools"), "refusals raise no error and create no tool run")
    check(reference["user_scores"] == SCORES, f"user scores {reference['user_scores']}")
    check(reference["thumbs_down_by_version"] == {OLD_VERSION: 15, NEW_VERSION: 10}, "thumbs-down flat by version")
    check(reference["thumbs_down_after_errored_run"] == BURST_DOWN, "6 thumbs-down follow an errored run")
    check(len(generated["feedback"]) == SCORES["up"] + SCORES["down"], "one feedback row per rated conversation")

    # 6.6: the answers
    check(answers["s1_signals"] == {"errored_root_runs": 13, "thumbs_down_conversations": 25, "thumbs_down_after_order_not_found": 16, "thumbs_down_on_wrong_return_window": 0}, "s1_signals")
    check(len(answers["s1_evaluator"]["flagged_trace_keys"]) == 11, "s1_evaluator")
    expected_sample = {"all_root_runs": {"scored": 260, "caught": 11}, "app_version_1_5_0": {"scored": 104, "caught": 11},
                       "sample_25_percent": {"scored": SAMPLED_RUNS, "caught": SAMPLED_CAUGHT}}
    if answers["s1_filter_sample"] != expected_sample:
        check(False, f"s1_filter_sample is {answers['s1_filter_sample']}; SAMPLING_SEED must catch exactly 3 (the smallest seed that does: {_find_sampling_seed(roots, planted)})")
    check(answers["s1_alert"] == {"background_max_in_5_minutes": 2, "burst_errors": 8, "threshold": 3, "failing_tool": "get_order_status"}, "s1_alert")
    check(answers["s1_routing"] == {"selected": 11}, "s1_routing")
    check(answers["s2_report"] == {"largest_category": "Order status and tracking", "largest_category_conversations": 78, "largest_category_share": 0.39,
                                    "highest_error_rate_subcategory": "Where is my order", "highest_error_rate": 0.196}, "s2_report")
    check(answers["s2_claim"] == {"conversations": 27, "error_rate": 0.0, "flagged": 11}, "s2_claim")
    check(answers["s3_evidence"] == {"missing_tool": "search_policy_docs", "under_run": "product-policy-specialist"}, "s3_evidence")
    check(answers["s3_triage"] == {"actions": ["apply_fix_and_add_examples", "review_pull_request", "save_for_later"]}, "s3_triage")
    check(all(action in TRIAGE_ACTIONS for action in answers["s3_triage"]["actions"]), "triage actions are among the four action codes")
    check(answers["s3_assertions"] == {"assertions": ["no_30_day_claim", "states_14_day_window"]}, "s3_assertions")
    check(reference["s3_followup"] == {"traces_per_set": 10, "before_fix_flagged": 4, "after_fix_flagged": 0}, "follow-up sets")
    transient = re.search(r"_TRANSIENT_STATUSES = \{([^}]*)\}", (REPO_ROOT / "agents" / "middleware" / "fault_tolerance.py").read_text(encoding="utf-8"))
    statuses = {int(s) for s in transient.group(1).split(",")} if transient else set()
    check(statuses & {402, 403, 429} == {429}, "of 402, 403 and 429 the retry middleware retries only 429")

    # 6.5: the report
    report = generated["insights_report"]
    expected_rates = {"Where is my order": 0.196, "What is in my order": 0.077, "Refund requests awaiting approval": 0.063, "Single-product spec lookups": 0.053,
                      "Compatibility between products": 0.04, "Order status and tracking": 0.128}
    subs = [c for c in report["clusters"] if c["parent_id"]]
    check(len(report["clusters"]) == 14 and len(subs) == 10 and sum(c["num_runs"] for c in subs) == N_CONVERSATIONS, "4 categories, 10 subcategories, 200 conversations")
    for cluster in report["clusters"]:
        if cluster["name"] in expected_rates:
            check(cluster["stats"]["error_rate"] == expected_rates[cluster["name"]], f"error rate of {cluster['name']}: {cluster['stats']['error_rate']}")
        elif cluster["parent_id"]:
            check(cluster["stats"]["error_rate"] == 0.0, f"error rate of {cluster['name']} should be 0.0")
    check(max(subs, key=lambda c: c["stats"]["cost_p50"])["name"] == "Compatibility between products", "compatibility has the highest median cost")
    text = json.dumps([generated["insights_report"], generated["engine_issues"], labels, answers, generated["followups"]])
    check("query_my_orders" not in text and "query_my_orders" not in json.dumps(runs), "the scoped SQL tool is not part of this agent configuration")
    issues = generated["engine_issues"]["issues"]
    check([(i["severity"], i["status"], i["type"]) for i in issues] == [(1, "open", "actionable"), (2, "fixing", "actionable"), (3, "watching", "finding")], "the three issues")
    check(_parse(issues[0]["first_seen_at"]) > RELEASE_AT, "issue 1 is first seen after 1.5.0 shipped")

    # every id in the data exists in the database
    for conv in conversations:
        check(conv["customer_id"] in src["customers"], f"unknown customer {conv['customer_id']}")
    for found in set(re.findall(r"ORD-\d{4}-\d{4}", json.dumps(runs) + text)):
        check(found in src["orders"], f"unknown order {found}")
    for found in set(re.findall(r"CUST-\d{3}", json.dumps(runs) + text)):
        check(found in src["customers"], f"unknown customer {found}")
    for found in set(re.findall(r"TECH-[A-Z]{3}-\d{3}", json.dumps(runs) + text)):
        check(found in src["products"], f"unknown product {found}")


# ---------------------------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------------------------


def _pretty(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


_SHARED_METADATA_KEYS = ("thread_id", "customer_id", "customer_segment", "app_version", "environment", "revision_id", "seed_trace_key", "synthetic")


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _pack_traces(runs: list[dict]) -> list[dict]:
    """Group runs by trace and store once what every run of a trace shares. `_unpack_traces` reverses it exactly."""
    traces = []
    for key, members in runs_by_trace(runs).items():
        shared = {k: members[0]["extra"]["metadata"][k] for k in _SHARED_METADATA_KEYS}
        packed = []
        for run in members:
            metadata = run["extra"]["metadata"]
            assert all(metadata[k] == v for k, v in shared.items()) and run["tags"] == members[0]["tags"] and run["trace_id"] == members[0]["trace_id"], key
            own = {k: v for k, v in metadata.items() if k not in shared}
            packed.append({**{k: v for k, v in run.items() if k not in ("trace_id", "dotted_order", "tags")}, "extra": {**run["extra"], "metadata": own}})
        traces.append({"trace_key": key, "trace_id": members[0]["trace_id"], "metadata": shared, "tags": members[0]["tags"], "runs": packed})
    return traces


def _unpack_traces(traces: list[dict]) -> list[dict]:
    """The flat run list of a packed file, with the shared values back on every run and `dotted_order` rebuilt."""
    runs = []
    for trace in traces:
        for packed in trace["runs"]:
            run = {"id": packed["id"], "trace_id": trace["trace_id"], "parent_run_id": packed["parent_run_id"], "dotted_order": ""}
            run.update({k: v for k, v in packed.items() if k not in ("id", "parent_run_id")})
            run["extra"] = {**packed["extra"], "metadata": {**trace["metadata"], **packed["extra"]["metadata"]}}
            run["tags"] = list(trace["tags"])
            runs.append(run)
    return rebuild_dotted_order(runs)


def _trace_lines(runs: list[dict]) -> list[str]:
    """JSON text of the packed traces, one run per line, without the surrounding brackets."""
    lines = []
    traces = _pack_traces(runs)
    for t, trace in enumerate(traces):
        head = _compact({k: v for k, v in trace.items() if k != "runs"})
        lines.append(head[:-1] + ',"runs":[')
        for i, run in enumerate(trace["runs"]):
            lines.append(_compact(run) + ("," if i < len(trace["runs"]) - 1 else "]}" + ("," if t < len(traces) - 1 else "")))
    return lines


def _seed_bytes(seed: dict) -> bytes:
    """The seed file: the meta block, then the traces with one run per line, then the feedback rows."""
    lines = ["{", f'"meta": {json.dumps(seed["meta"], ensure_ascii=True)},', '"traces": [']
    lines += _trace_lines(seed["runs"])
    lines += ["],", '"feedback": [']
    lines += [_compact(row) + ("," if i < len(seed["feedback"]) - 1 else "") for i, row in enumerate(seed["feedback"])]
    lines += ["]", "}"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _followup_bytes(followups: dict) -> bytes:
    lines = ["{", f'"_about": {json.dumps(followups["_about"], ensure_ascii=True)},']
    for label in ("before_fix", "after_fix"):
        part = followups[label]
        lines.append(f'"{label}": {{"app_version": {json.dumps(part["app_version"])}, "revision_id": {json.dumps(part["revision_id"])}, "traces": [')
        lines += _trace_lines(part["runs"])
        lines.append("]}" + ("," if label == "before_fix" else ""))
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def seed_files(generated: dict | None = None) -> dict[str, bytes]:
    """File name -> bytes for the seven generated files of `workshop_modules/module_7/data/`."""
    generated = generated or generate_seed()
    return {
        SEED_FILE: _seed_bytes(generated),
        LABELS_FILE: _pretty(generated["labels"]),
        ANSWERS_FILE: _pretty(generated["answers"]),
        HASHES_FILE: _pretty(generated["answer_hashes"]),
        FOLLOWUP_FILE: _followup_bytes(generated["followups"]),
        INSIGHTS_FILE: _pretty(generated["insights_report"]),
        ENGINE_FILE: _pretty(generated["engine_issues"]),
    }


# ---------------------------------------------------------------------------------------------
# Loading, shifting, re-keying
# ---------------------------------------------------------------------------------------------

_TIME_KEYS = {"start_time", "end_time", "created_at", "updated_at", "first_seen_at", "last_seen_at", "watching_since", "fix_dispatched_at", "run_start_time",
              "oldest_root_start", "newest_root_start", "release_1_5_0_at"}


def _shift_times(value: Any, delta: timedelta) -> Any:
    """Return a copy of a JSON-like value with every timestamp field moved by `delta`, keeping each one's format."""
    if isinstance(value, list):
        return [_shift_times(item, delta) for item in value]
    if not isinstance(value, dict):
        return value
    shifted = {}
    for key, item in value.items():
        if key in _TIME_KEYS and isinstance(item, str):
            moved = _parse(item) + delta
            shifted[key] = _iso_z(moved) if item.endswith("Z") else _iso(moved)
        elif key in ("inputs", "outputs", "extra", "tags"):
            shifted[key] = item  # payloads carry no timestamps; share them instead of copying
        else:
            shifted[key] = _shift_times(item, delta)
    return shifted


def shift_to_now(seed: dict, now: datetime | None = None, newest_age: timedelta = NEWEST_RUN_AGE) -> dict:
    """Return a copy of the seed whose newest root run started `newest_age` (5 minutes) before `now`.

    Every other timestamp keeps its distance to that run, so the 20-hour day always reads as "the last
    20 hours". `seed["meta"]["clock"]["shifted_by_seconds"]` records the total shift, which
    `load_insights_report()` and `load_engine_issues()` use to move the fixtures by the same amount.
    """
    now = now or datetime.now(timezone.utc)
    newest = max(_parse(r["start_time"]) for r in seed["runs"] if r["parent_run_id"] is None)
    delta = (now - newest_age) - newest
    shifted = _shift_times(seed, delta)
    shifted["meta"]["clock"]["shifted_by_seconds"] = seed["meta"]["clock"]["shifted_by_seconds"] + delta.total_seconds()
    rebuild_dotted_order(shifted["runs"])
    return shifted


_shift_to_now = shift_to_now  # `load_seed` has a parameter of the same name


def remap_ids(seed: dict, new_id: Callable[[datetime], Any] | None = None, thread_suffix: str | None = None) -> dict:
    """Return a copy of the seed with a new id for every run, ready for one upload.

    A re-upload with the committed ids would collide with the first, so every upload gets its own ids:
    `new_id(start_time)` is called once per run (default: a UUID version 7 for that time, built with the
    standard library; the uploader passes `langsmith.uuid.uuid7_from_datetime`). A root run's new id is
    also its `trace_id`. `thread_suffix`, when given, is appended to every `thread_id` so a second upload
    does not join the conversations of the first. `dotted_order` is rebuilt, and the feedback rows follow.
    """
    new_id = new_id or uuid7_at
    mapping = {run["id"]: str(new_id(_parse(run["start_time"]))) for run in seed["runs"]}
    remapped = {**seed, "meta": copy.deepcopy(seed["meta"]), "runs": [], "feedback": []}
    for run in seed["runs"]:
        extra = {**run["extra"], "metadata": dict(run["extra"]["metadata"])}
        if thread_suffix:
            extra["metadata"]["thread_id"] += thread_suffix
        remapped["runs"].append({**run, "id": mapping[run["id"]], "trace_id": mapping[run["trace_id"]],
                                 "parent_run_id": mapping[run["parent_run_id"]] if run["parent_run_id"] else None, "extra": extra})
    for row in seed["feedback"]:
        remapped["feedback"].append({**row, "run_id": mapping[row["run_id"]], "trace_id": mapping[row["trace_id"]],
                                     "thread_id": row["thread_id"] + (thread_suffix or "")})
    rebuild_dotted_order(remapped["runs"])
    return remapped


def load_seed(path: str | Path | None = None, shift_to_now: bool = True) -> dict:
    """Load the committed seed. With `shift_to_now` (the default) the newest root run started 5 minutes ago.

    No network, no key. Returns `{"meta": ..., "runs": [...], "feedback": [...]}`; see the module docstring.
    """
    stored = json.loads(Path(path or DATA / SEED_FILE).read_text(encoding="utf-8"))
    seed = {"meta": stored["meta"], "runs": _unpack_traces(stored["traces"]), "feedback": stored["feedback"]}
    return _shift_to_now(seed) if shift_to_now else seed


def _shift_of(seed: dict | None) -> timedelta:
    return timedelta(seconds=seed["meta"]["clock"]["shifted_by_seconds"]) if seed else timedelta(0)


def load_labels(path: str | Path | None = None) -> dict:
    """Load `seed_labels.json`: the ground truth per conversation. It exists only because the data is synthetic."""
    return json.loads(Path(path or DATA / LABELS_FILE).read_text(encoding="utf-8"))


def load_insights_report(seed: dict | None = None, path: str | Path | None = None) -> dict:
    """Load the sample Insights report as a dictionary, its timestamps moved with `seed` when one is given.

    The result has the REST shape of a report: `langsmith.schemas.InsightsReportResult(**result)` loads it.
    It is a hand-built sample generated from the seed, not output of the product.
    """
    return _shift_times(json.loads(Path(path or DATA / INSIGHTS_FILE).read_text(encoding="utf-8")), _shift_of(seed))


def load_engine_issues(seed: dict | None = None, path: str | Path | None = None) -> dict:
    """Load the sample Engine issue board (`issues`, `evidence`, `offline_examples`), timestamps moved with `seed`.

    `result["issues"]` has the type a live `client.list_project_issues(...)` call returns: a list of dictionaries.
    It is a hand-built sample generated from the seed, not output of the product.
    """
    return _shift_times(json.loads(Path(path or DATA / ENGINE_FILE).read_text(encoding="utf-8")), _shift_of(seed))


def load_followups(seed: dict | None = None, path: str | Path | None = None) -> dict:
    """Load the two follow-up sets (`before_fix`, `after_fix`), timestamps moved with `seed` when one is given."""
    stored = json.loads(Path(path or DATA / FOLLOWUP_FILE).read_text(encoding="utf-8"))
    follow = {"_about": stored["_about"]}
    for label in ("before_fix", "after_fix"):
        part = stored[label]
        follow[label] = {"app_version": part["app_version"], "revision_id": part["revision_id"], "runs": _unpack_traces(part["traces"])}
    follow = _shift_times(follow, _shift_of(seed))
    for label in ("before_fix", "after_fix"):
        rebuild_dotted_order(follow[label]["runs"])
    return follow


# ---------------------------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------------------------


def describe(seed: dict) -> dict:
    """Print what the seed contains and return the same numbers as a dictionary."""
    roots = root_runs(seed)
    threads = {r["extra"]["metadata"]["thread_id"] for r in roots}
    versions: dict[str, int] = {}
    for root in roots:
        versions[root["extra"]["metadata"]["app_version"]] = versions.get(root["extra"]["metadata"]["app_version"], 0) + 1
    oldest, newest = _parse(roots[0]["start_time"]), _parse(roots[-1]["start_time"])
    hours = int(-(-(newest - oldest).total_seconds() // 3600))
    turns: dict[str, int] = {}
    for root in roots:
        turns[root["extra"]["metadata"]["thread_id"]] = turns.get(root["extra"]["metadata"]["thread_id"], 0) + 1
    two = sum(1 for n in turns.values() if n == 2)
    summary = {"conversations": len(threads), "traces": len(roots), "runs": len(seed["runs"]), "hours": hours, "root_runs_by_version": dict(sorted(versions.items())),
               "two_turn_conversations": two, "user_scores": len(seed["feedback"])}
    print(f"{len(threads)} conversations, {len(roots)} traces (root runs), {len(seed['runs']):,} runs, last {hours} hours")
    print(f"  conversations with two turns: {two}; with one turn: {len(threads) - two}")
    print("  versions: " + " and ".join(f"{v} ({n} traces)" for v, n in sorted(versions.items())))
    print(f"  from {oldest:%Y-%m-%d %H:%M} to {newest:%Y-%m-%d %H:%M} UTC; user scores on {len(seed['feedback'])} conversations")
    print(f"  synthetic data: every run has the tag {SEED_TAG} and the metadata synthetic: true")
    return summary


def print_trace(seed_or_runs, key: str) -> None:
    """Print one trace as a tree, then the customer's message, the reply and the root run's metadata keys.

    `key` is a trace key such as "t-0042", or the id of any run in the trace.
    """
    members = trace_runs(seed_or_runs, key)
    if not members:
        print(f"No trace {key!r} in this data.")
        return
    root = members[0]
    metadata = root["extra"]["metadata"]
    children: dict[str, list[dict]] = {}
    for run in members[1:]:
        children.setdefault(run["parent_run_id"], []).append(run)
    print(f"{metadata['seed_trace_key']}  {metadata['thread_id']}  app_version {metadata['app_version']}  customer {metadata['customer_id']}  "
          f"started {_parse(root['start_time']):%Y-%m-%d %H:%M:%S} UTC  ({len(members)} runs)")

    def line(run: dict, prefix: str, last: bool, top: bool) -> None:
        detail = ""
        if run["run_type"] == "llm":
            usage = run["extra"]["metadata"]["usage_metadata"]
            detail = f"  {run['extra']['metadata']['ls_model_name']}  {usage['input_tokens']:,} in / {usage['output_tokens']:,} out"
        elif run["name"] == "task":
            detail = f"  -> {run['inputs'].get('subagent_type')}"
        elif run["run_type"] == "tool":
            detail = "  " + _clip(json.dumps(run["inputs"]), 60)
        if run["error"]:
            detail += "  ERROR: " + run["error"]
        branch = "" if top else ("└── " if last else "├── ")
        print(f"{prefix}{branch}{run['name']} [{run['run_type']}] {_duration(run):.2f}s{detail}")
        kids = children.get(run["id"], [])
        for i, kid in enumerate(kids):
            line(kid, prefix + ("" if top else ("    " if last else "│   ")), i == len(kids) - 1, False)

    line(root, "", True, True)
    print(f"Customer: {question_text(root)}")
    reply = reply_text(root)
    if root["error"]:
        print("Agent:    (no reply: the run failed)")
    elif reply:
        print(f"Agent:    {reply}")
    else:
        last = root["outputs"]["messages"][-1]
        calls = ", ".join(c["name"] for c in last.get("tool_calls") or [])
        print(f"Agent:    (no reply yet: the turn paused on the tool call {calls}, which waits for human approval)")
    print("Metadata keys on the root run: " + ", ".join(sorted(metadata)))
