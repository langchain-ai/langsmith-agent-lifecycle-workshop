# agents/supervisor_hitl_agent.py
"""
Customer Verification + Supervisor Agent with HITL

This module creates a complete customer support agent that combines:
- Query classification (does this need identity verification?)
- Human-in-the-loop (HITL) email collection and validation
- Supervisor agent routing to specialized sub-agents

This demonstrates LangGraph primitives for complex orchestration:
- StateGraph with custom state schema (IntermediateState with customer_id)
- Command for explicit routing control
- interrupt() for HITL pauses
- Subgraphs (supervisor agent as a node)
"""

from typing import Literal, NamedTuple

from langchain.agents import AgentState
from langchain.chat_models import init_chat_model
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import Annotated, TypedDict

# Import other agent factory functions
from agents.db_agent import create_db_agent
from agents.docs_agent import create_docs_agent
from agents.supervisor_agent import create_supervisor_agent
from config import DEFAULT_MODEL
from tools import get_customer_orders
from tools.database import get_database

# ============================================================================
# CUSTOM STATE SCHEMA
# ============================================================================


class IntermediateState(AgentState):
    """Intermediate AgentState with customer_id for verification tracking.

    AgentState includes a `messages` key with proper reducers by default.
    Shared keys automatically flow between parent and subgraphs.
    """

    customer_id: str


# ============================================================================
# HELPER SCHEMAS AND FUNCTIONS
# ============================================================================


class QueryClassification(TypedDict):
    """Classification of whether customer identity verification is required."""

    reasoning: Annotated[
        str, ..., "Brief explanation of why verification is or isn't needed"
    ]
    requires_verification: Annotated[
        bool,
        ...,
        "True if the query requires knowing customer identity (e.g., 'my orders', 'my account', 'my purchases'). False for general questions (product info, policies, how-to questions).",
    ]


class EmailExtraction(TypedDict):
    """Schema for extracting email from user message."""

    email: Annotated[
        str,
        ...,
        "The email address extracted from the message, or empty string if none found",
    ]


class CustomerInfo(NamedTuple):
    """Customer information returned from validation."""

    customer_id: str
    customer_name: str


def classify_query_intent(query: str) -> QueryClassification:
    """Classify whether a query requires customer identity verification.

    Args:
        query: The user's query string

    Returns:
        QueryClassification dict with reasoning and requires_verification fields
    """
    llm = init_chat_model(DEFAULT_MODEL)
    structured_llm = llm.with_structured_output(QueryClassification)
    classification_prompt = """Analyze the user's query to determine if it requires knowing their customer identity in order to answer the question."""

    classification = structured_llm.invoke(
        [
            {"role": "system", "content": classification_prompt},
            {"role": "user", "content": "Query: " + query},
        ]
    )

    return classification


def create_email_extractor():
    """Create an LLM configured to extract emails from natural language."""
    llm = init_chat_model(DEFAULT_MODEL)
    return llm.with_structured_output(EmailExtraction)


def validate_customer_email(email: str, db: SQLDatabase) -> CustomerInfo | None:
    """Validate email format and lookup customer in database.

    Args:
        email: Email address to validate
        db: SQLDatabase connection

    Returns:
        CustomerInfo with customer_id and customer_name if valid, None otherwise
    """
    # Check email format
    if not email or "@" not in email:
        return None

    # Lookup in database
    result = db._execute(
        f"SELECT customer_id, name FROM customers WHERE email = '{email}'"
    )

    # Convert SQLDatabase query results to list of tuples (values only)
    result = [tuple(row.values()) for row in result]

    if not result:
        return None

    customer_id, customer_name = result[0]
    return CustomerInfo(customer_id=customer_id, customer_name=customer_name)


# ============================================================================
# GRAPH NODES
# ============================================================================


def query_router(
    state: IntermediateState,
) -> Command[Literal["verify_customer", "supervisor_agent"]]:
    """Route query based on verification needs.

    Logic:
    1. If customer already verified from earlier in the thread → supervisor_agent
    2. If query needs verification → verify_customer
    3. Otherwise → supervisor_agent
    """
    # Already verified? Skip to supervisor agent
    if state.get("customer_id"):
        return Command(goto="supervisor_agent")

    # Not already verified - classify query to see if verification is needed
    last_message = state["messages"][-1]
    query_classification = classify_query_intent(last_message.content)

    # Route based on classification
    if query_classification.get("requires_verification"):
        return Command(goto="verify_customer")
    return Command(goto="supervisor_agent")


def verify_customer(
    state: IntermediateState,
) -> Command[Literal["supervisor_agent", "collect_email"]]:
    """Ensure we have a valid customer email and set the `customer_id` in state.

    Uses Command to explicitly route based on result.
    """
    # Get last message from user
    last_message = state["messages"][-1]

    # Try to extract email using structured output
    email_extractor = create_email_extractor()
    extraction = email_extractor.invoke([last_message])

    # If we have an email, attempt to validate it
    if extraction["email"]:
        db = get_database()
        customer = validate_customer_email(extraction["email"], db)

        if customer:
            # Success! Email verified → Go to supervisor
            return Command(
                update={
                    "customer_id": customer.customer_id,
                    "messages": [
                        AIMessage(
                            content=f"✓ Verified! Welcome back, {customer.customer_name}, your customer ID is {customer.customer_id}."
                        )
                    ],
                },
                goto="supervisor_agent",
            )
        else:
            # Email not found → Try again
            return Command(
                update={
                    "messages": [
                        AIMessage(
                            content=f"I couldn't find '{extraction['email']}' in our system. Please check and try again."
                        )
                    ]
                },
                goto="collect_email",
            )

    # No email detected → Ask for it
    return Command(
        update={
            "messages": [
                AIMessage(
                    content="To access information about your account or orders, please provide your email address."
                )
            ]
        },
        goto="collect_email",
    )


def collect_email(state: IntermediateState) -> Command[Literal["verify_customer"]]:
    """Dedicated node for collecting human input via interrupt."""
    user_input = interrupt(value="Please provide your email:")
    return Command(
        update={"messages": [HumanMessage(content=user_input)]}, goto="verify_customer"
    )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_supervisor_hitl_agent(
    db_agent=None,
    docs_agent=None,
    use_checkpointer: bool = True,
):
    """Create customer verification + supervisor agent with HITL.

    This creates a complete verification graph that:
    - Classifies if query needs identity verification
    - Collects and validates customer email (HITL)
    - Routes to supervisor agent for query handling
    - Remembers customer_id across conversation

    Args:
        db_agent: Optional pre-configured database agent. If None, creates a standard db_agent.
                 This allows swapping in improved agents (e.g., sql_agent) without rewriting logic.
        docs_agent: Optional pre-configured documents agent. If None, creates a standard docs_agent.
        use_checkpointer: Whether to include a checkpointer for persistence.
                         - True (default): Use MemorySaver for development/notebooks
                         - False: No checkpointer (for LangGraph API deployment)

    Returns:
        Compiled verification graph with HITL and supervisor routing.

    Examples:
        >>> # Standard usage (backward compatible)
        >>> agent = create_supervisor_hitl_agent()

        >>> # With improved SQL agent (Module 2, Section 2)
        >>> from agents import create_sql_agent
        >>> sql_agent = create_sql_agent(state_schema=IntermediateState)
        >>> agent = create_supervisor_hitl_agent(db_agent=sql_agent)
    """
    # Instantiate sub-agents with shared state schema (if not provided)
    # The db_agent gets get_customer_orders, which uses ToolRuntime to access customer_id
    if db_agent is None:
        db_agent = create_db_agent(
            state_schema=IntermediateState,
            additional_tools=[get_customer_orders],
            use_checkpointer=use_checkpointer,
        )

    if docs_agent is None:
        docs_agent = create_docs_agent(use_checkpointer=use_checkpointer)

    # Instantiate supervisor agent (which wraps the sub-agents as tools)
    supervisor_agent = create_supervisor_agent(
        db_agent=db_agent,
        docs_agent=docs_agent,
        state_schema=IntermediateState,
        use_checkpointer=use_checkpointer,
    )

    # Build the verification graph
    workflow = StateGraph(
        input_schema=AgentState,
        state_schema=IntermediateState,
        output_schema=AgentState,
    )

    # Add nodes
    workflow.add_node("query_router", query_router)
    workflow.add_node("verify_customer", verify_customer)
    workflow.add_node("collect_email", collect_email)
    workflow.add_node("supervisor_agent", supervisor_agent)

    # Set entry point
    workflow.add_edge(START, "query_router")

    # Compile with optional checkpointer
    if use_checkpointer:
        return workflow.compile(checkpointer=MemorySaver())
    else:
        return workflow.compile()
