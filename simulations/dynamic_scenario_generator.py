"""
Dynamic scenario generator for simulation system.

Queries the TechHub SQLite DB to pick real customers + their order history,
selects a weighted archetype, and calls an LLM to generate a realistic
opening query grounded in actual data.
"""

import hashlib
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ============================================================================
# Archetype Definitions
# ============================================================================

@dataclass
class Archetype:
    archetype_id: str
    description: str
    requires_verification: bool
    primary_agent: str
    # Sentiment weights: [neutral, positive, negative] — must sum to 100
    sentiment_weights: list[int]
    typical_queries: list[str]
    tags: list[str]
    segment_filter: Optional[str] = None  # e.g. "Corporate" to limit to one segment
    hint: str = ""  # Archetype-specific LLM hint


ARCHETYPES: list[Archetype] = [
    Archetype(
        archetype_id="order_status_check",
        description="Customer checking on the status of a recent order.",
        requires_verification=True,
        primary_agent="DB/SQL",
        sentiment_weights=[60, 25, 15],
        typical_queries=["Where is my order?", "Has my package shipped?", "When will I receive my order?"],
        tags=["order_status", "shipping"],
        hint="Ask about a specific recent order by product name.",
    ),
    Archetype(
        archetype_id="delayed_order_complaint",
        description="Customer upset about a delayed or late delivery.",
        requires_verification=True,
        primary_agent="DB/SQL",
        sentiment_weights=[10, 0, 90],
        typical_queries=["My order is late!", "Where is my package?", "This is unacceptable!"],
        tags=["complaint", "shipping", "delay"],
        hint="Express frustration about an order that seems overdue or still in processing.",
    ),
    Archetype(
        archetype_id="return_exchange_request",
        description="Customer requesting a return or exchange for a recent purchase.",
        requires_verification=True,
        primary_agent="DB+Docs",
        sentiment_weights=[20, 0, 80],
        typical_queries=["How do I return this?", "Can I exchange my order?", "I need a refund"],
        tags=["return", "exchange", "refund"],
        hint="Reference a specific product from a recent order and ask about the return process.",
    ),
    Archetype(
        archetype_id="spending_history_review",
        description="Customer reviewing their purchase history or total spending.",
        requires_verification=True,
        primary_agent="SQL",
        sentiment_weights=[80, 20, 0],
        typical_queries=["How much have I spent?", "Can I see my order history?", "What have I purchased?"],
        tags=["account", "history", "spending"],
        hint="Ask to see a summary of past purchases or spending.",
    ),
    Archetype(
        archetype_id="product_research",
        description="Customer researching products before making a purchase decision.",
        requires_verification=False,
        primary_agent="Docs",
        sentiment_weights=[60, 40, 0],
        typical_queries=["What are the specs?", "Which laptop is best for me?", "Compare these products"],
        tags=["product_research", "pre_purchase"],
        hint="Ask about specific product features or comparisons — no personal account needed.",
    ),
    Archetype(
        archetype_id="policy_question",
        description="Customer asking about store policies (shipping, warranty, returns).",
        requires_verification=False,
        primary_agent="Docs",
        sentiment_weights=[70, 30, 0],
        typical_queries=["What is your return policy?", "How long is the warranty?", "Do you offer free shipping?"],
        tags=["policy", "information"],
        hint="Ask a general policy question that doesn't require account access.",
    ),
    Archetype(
        archetype_id="product_spec_deep_dive",
        description="Customer diving deep into technical specifications of a specific product.",
        requires_verification=False,
        primary_agent="Docs",
        sentiment_weights=[50, 50, 0],
        typical_queries=["What are the RAM options?", "Does it support 4K?", "What ports does it have?"],
        tags=["specs", "technical", "product_research"],
        hint="Ask detailed technical questions about a specific product category (laptop, monitor, keyboard, etc.).",
    ),
    Archetype(
        archetype_id="corporate_bulk_inquiry",
        description="Corporate customer asking about bulk purchasing or volume discounts.",
        requires_verification=True,
        primary_agent="SQL",
        sentiment_weights=[90, 10, 0],
        typical_queries=["We need 20 units", "Do you offer bulk pricing?", "What's the lead time for large orders?"],
        tags=["corporate", "bulk", "b2b"],
        segment_filter="Corporate",
        hint="Mention needing multiple units for a business/team and ask about availability or pricing.",
    ),
    Archetype(
        archetype_id="warranty_claim",
        description="Customer filing or inquiring about a warranty claim.",
        requires_verification=True,
        primary_agent="DB+Docs",
        sentiment_weights=[25, 0, 75],
        typical_queries=["My product stopped working", "I need to file a warranty claim", "The screen is broken"],
        tags=["warranty", "support", "complaint"],
        hint="Describe a product issue with something from a recent order and ask about warranty coverage.",
    ),
    Archetype(
        archetype_id="cancelled_order_confusion",
        description="Customer confused or upset about a cancelled order.",
        requires_verification=True,
        primary_agent="DB",
        sentiment_weights=[15, 0, 85],
        typical_queries=["Why was my order cancelled?", "I didn't cancel that!", "Can you reinstate my order?"],
        tags=["cancellation", "complaint", "order_issue"],
        hint="Ask about a cancelled order — express confusion or frustration about why it was cancelled.",
    ),
    Archetype(
        archetype_id="home_office_setup",
        description="Home office customer looking to set up or upgrade their workspace.",
        requires_verification=False,
        primary_agent="Docs",
        sentiment_weights=[40, 60, 0],
        typical_queries=["Best monitor for home office?", "What keyboard do you recommend?", "Setting up ergonomic workspace"],
        tags=["home_office", "setup", "recommendations"],
        segment_filter="Home Office",
        hint="Ask for product recommendations to build or upgrade a home office setup.",
    ),
    Archetype(
        archetype_id="loyalty_inquiry",
        description="Customer asking about loyalty points, rewards, or account benefits.",
        requires_verification=True,
        primary_agent="SQL",
        sentiment_weights=[50, 50, 0],
        typical_queries=["Do I have any rewards?", "How many points do I have?", "What benefits do I get?"],
        tags=["loyalty", "account", "rewards"],
        hint="Ask about loyalty points or rewards based on total spending or order history.",
    ),
]

# Communication styles keyed by (segment, sentiment)
COMMUNICATION_STYLES: dict[tuple[str, str], str] = {
    ("Consumer", "neutral"): "Direct and conversational",
    ("Consumer", "positive"): "Friendly and casual",
    ("Consumer", "negative"): "Short and frustrated",
    ("Corporate", "neutral"): "Formal and business-oriented",
    ("Corporate", "positive"): "Professional and business-focused",
    ("Corporate", "negative"): "Formal but demanding, business-critical",
    ("Home Office", "neutral"): "Informal and practical",
    ("Home Office", "positive"): "Friendly and informal",
    ("Home Office", "negative"): "Frustrated but informal",
}


# ============================================================================
# DB helpers
# ============================================================================

def _fetch_customer(db_path: Path, segment_filter: Optional[str] = None) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        if segment_filter:
            row = conn.execute(
                "SELECT customer_id, name, email, segment FROM customers WHERE segment = ? ORDER BY RANDOM() LIMIT 1",
                (segment_filter,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT customer_id, name, email, segment FROM customers ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
        return {"customer_id": row[0], "name": row[1], "email": row[2], "segment": row[3]}
    finally:
        conn.close()


def _fetch_recent_orders(db_path: Path, customer_id: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT o.order_id, o.status, o.order_date,
                   GROUP_CONCAT(p.name, ', ') AS products
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.customer_id = ?
            GROUP BY o.order_id
            ORDER BY o.order_date DESC
            LIMIT 3
            """,
            (customer_id,),
        ).fetchall()
        return [
            {"order_id": r[0], "status": r[1], "order_date": r[2], "products": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


def _fetch_order_count(db_path: Path, customer_id: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


# ============================================================================
# Archetype selection
# ============================================================================

def _select_archetype(segment: str, has_orders: bool) -> Archetype:
    """
    Pick a weighted-random archetype compatible with the customer's segment
    and order history.
    """
    candidates = []
    for arch in ARCHETYPES:
        # Skip segment-filtered archetypes that don't match
        if arch.segment_filter and arch.segment_filter != segment:
            continue
        # Skip order-dependent archetypes if customer has no orders
        if not has_orders and arch.requires_verification:
            continue
        candidates.append(arch)

    # If no candidates fall through (edge case), fall back to policy/product archetypes
    if not candidates:
        candidates = [a for a in ARCHETYPES if not a.requires_verification]

    # Weight by how likely each archetype is for this segment
    # Corporate: prefer business-oriented archetypes; Home Office: prefer setup/docs
    segment_weights = {
        "Corporate": {
            "corporate_bulk_inquiry": 3.0,
            "spending_history_review": 2.0,
            "order_status_check": 1.5,
        },
        "Home Office": {
            "home_office_setup": 3.0,
            "product_spec_deep_dive": 2.0,
            "product_research": 1.5,
        },
        "Consumer": {},  # uniform — no boosting
    }
    boosts = segment_weights.get(segment, {})
    weights = [boosts.get(a.archetype_id, 1.0) for a in candidates]

    return random.choices(candidates, weights=weights, k=1)[0]


def _pick_sentiment(archetype: Archetype) -> str:
    choices = ["neutral", "positive", "negative"]
    return random.choices(choices, weights=archetype.sentiment_weights, k=1)[0]


# ============================================================================
# LLM query generation
# ============================================================================

def _format_orders(orders: list[dict]) -> str:
    if not orders:
        return "No recent orders."
    lines = []
    for o in orders:
        lines.append(f"  {o['order_id']} ({o['status']}, {o['order_date']}): {o['products']}")
    return "\n".join(lines)


async def _generate_opening_query(
    llm,
    customer: dict,
    orders: list[dict],
    order_count: int,
    archetype: Archetype,
    sentiment: str,
) -> str:
    prompt = f"""You are generating a realistic customer support opening message for a TechHub e-commerce customer.

CUSTOMER: {customer['name']}, {customer['segment']} segment, {order_count} total orders
RECENT ORDERS:
{_format_orders(orders)}

CONVERSATION TYPE: {archetype.description}
TONE: {sentiment}

Generate a single realistic 1-3 sentence opening message. Reference specific order history when relevant. Match the communication style for a {customer['segment']} customer with {sentiment} sentiment. Do not include preamble or quotation marks.
Hint: {archetype.hint}

Your response (just the customer's message):"""

    response = await llm.ainvoke(prompt, config={"callbacks": []})
    return response.content.strip().strip('"').strip("'")


# ============================================================================
# Public API
# ============================================================================

async def generate_dynamic_scenario(db_path: Path, llm) -> dict:
    """
    Query DB, pick archetype, call LLM → return run_scenario()-compatible dict.
    """
    # Pick archetype first (might require a specific segment)
    # We do a temporary segment-agnostic archetype selection, then fetch matching customer
    # Actually, we need to know segment first to filter archetypes. Fetch customer first.
    # But some archetypes are segment-filtered — so if archetype requires Corporate, we re-fetch.
    # Simple approach: pick customer → pick archetype → if archetype has segment_filter that
    # doesn't match, re-pick archetype (not re-pick customer).

    customer = _fetch_customer(db_path)
    orders = _fetch_recent_orders(db_path, customer["customer_id"])
    order_count = _fetch_order_count(db_path, customer["customer_id"])

    archetype = _select_archetype(customer["segment"], has_orders=order_count > 0)
    sentiment = _pick_sentiment(archetype)

    # Generate opening query via LLM
    initial_query = await _generate_opening_query(
        llm=llm,
        customer=customer,
        orders=orders,
        order_count=order_count,
        archetype=archetype,
        sentiment=sentiment,
    )

    # Build short hash for unique scenario_id
    hash_input = f"{archetype.archetype_id}_{customer['customer_id']}_{initial_query[:30]}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:6]

    communication_style = COMMUNICATION_STYLES.get(
        (customer["segment"], sentiment),
        "Direct and conversational",
    )

    return {
        "scenario_id": f"dynamic_{archetype.archetype_id}_{customer['customer_id']}_{short_hash}",
        "customer": {
            "email": customer["email"],
            "name": customer["name"],
            "customer_id": customer["customer_id"],
            "segment": customer["segment"],
        },
        "persona": {
            "description": f"{customer['segment']} customer. {archetype.description}",
            "communication_style": communication_style,
            "sentiment": sentiment,
            "typical_queries": archetype.typical_queries,
        },
        "initial_query": initial_query,
        "requires_verification": archetype.requires_verification,
        "tags": archetype.tags + [f"segment:{customer['segment']}", "dynamic", f"archetype:{archetype.archetype_id}"],
        # Extra keys for thread metadata enrichment (not read by run_scenario itself)
        "_archetype_id": archetype.archetype_id,
    }
