"""
Runtime Model Configuration Example

This demonstrates how to configure models at runtime using LangSmith Studio's
"configurable Assistants" feature or the LangGraph SDK.

All agents in this workshop support runtime model configuration via the shared
Context class defined in config.py.
"""

import os
import uuid

from agents import create_supervisor_hitl_agent, create_db_agent
from config import Context

# ============================================================================
# Example 1: Simple Agent with Runtime Model Configuration
# ============================================================================

# Create agent (uses DEFAULT_MODEL by default)
db_agent = create_db_agent(use_checkpointer=False)

# Invoke with different model using SDK
thread_id = str(uuid.uuid4())
result = db_agent.invoke(
    {"messages": [{"role": "user", "content": "What products are in stock?"}]},
    config={
        "configurable": {
            "thread_id": thread_id,
            "model": "openai:gpt-5-nano",  # Override to use GPT-5 Nano instead of default
        },
        "metadata": {
            "thread_id": thread_id,
            "environment": os.getenv("ENVIRONMENT", "production"),
        },
    },
)

print(result["messages"][-1].content)


# ============================================================================
# Example 2: HITL Agent with Model Cascading
# ============================================================================

# Create the full HITL agent (includes supervisor and sub-agents)
agent = create_supervisor_hitl_agent(use_checkpointer=False)

# When you configure the HITL agent's model, it cascades through the entire hierarchy:
# - The HITL agent's helper functions (classify_query_intent, email extraction) use it
# - The supervisor agent uses it
# - The db_agent uses it
# - The docs_agent uses it
thread_id = str(uuid.uuid4())
result = agent.invoke(
    {
        "messages": [
            {"role": "user", "content": "What's the status of order ORD-2024-0001?"}
        ]
    },
    config={
        "configurable": {
            "thread_id": thread_id,
            "model": "anthropic:claude-sonnet-4-5",  # Override to use Sonnet instead of Haiku
        },
        "metadata": {
            "thread_id": thread_id,
            "environment": os.getenv("ENVIRONMENT", "production"),
        },
    },
)

print(result["messages"][-1].content)


# ============================================================================
# Example 3: Using in LangSmith Studio
# ============================================================================

"""
When you deploy ANY agent to LangSmith, you can select the model from a dropdown in the UI:

1. Deploy an agent:
   $ langgraph deploy

2. In LangSmith Studio, go to your deployment

3. In the configuration panel, you'll see a "model" dropdown with these options:
   - anthropic:claude-haiku-4-5 (default, fast and cost-effective)
   - anthropic:claude-sonnet-4-5 (more capable)
   - openai:gpt-5-mini (fast OpenAI option)
   - openai:gpt-5-nano (lightweight OpenAI option)

4. Select a model and interact with your agent - all sub-agents automatically use
   the same model you selected!

The available models are defined in config.Context as Literal types, which enables
the type-safe dropdown in LangSmith Studio.
"""


# ============================================================================
# Example 4: Testing Different Models Locally
# ============================================================================


def test_agent_with_models():
    """Test the same query with different models to compare responses."""
    agent = create_db_agent(use_checkpointer=False)
    query = {"messages": [{"role": "user", "content": "List all laptop products"}]}

    models = [
        "anthropic:claude-haiku-4-5",
        "anthropic:claude-sonnet-4-5",
        "openai:gpt-5-mini",
    ]

    for model in models:
        print(f"\n{'=' * 60}")
        print(f"Testing with model: {model}")
        print(f"{'=' * 60}\n")

        thread_id = str(uuid.uuid4())
        result = agent.invoke(
            query,
            config={
                "configurable": {"thread_id": thread_id, "model": model},
                "metadata": {
                    "thread_id": thread_id,
                    "environment": os.getenv("ENVIRONMENT", "production"),
                },
            },
        )
        print(result["messages"][-1].content)


# Uncomment to run the comparison:
# test_agent_with_models()


# ============================================================================
# Key Takeaways
# ============================================================================

"""
1. ALL agents support runtime model configuration (db, docs, sql, supervisor, HITL)

2. Configuration cascades automatically through agent hierarchies via LangGraph's
   config propagation mechanism

3. Models are constrained to a curated list (Literal types in Context class) for
   safety and consistency

4. You can configure models:
   - At invocation time via config parameter (SDK)
   - In LangSmith Studio via dropdown (production deployments)
   - In notebooks/scripts for testing and comparison

5. No code changes needed to switch models - configuration is external to agent logic
"""
