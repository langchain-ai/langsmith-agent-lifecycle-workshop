# TechHub Agent Simulation System

Automated system for generating realistic customer support traces for demo and testing purposes against the deployed `supervisor_hitl_sql_agent`.

## Overview

This simulation system creates realistic multi-turn conversations with the deployed TechHub agent using:
- **Dynamic scenario generation** — queries the real TechHub SQLite DB to pick customers and their order history, then uses an LLM to generate grounded opening queries
- **12 scenario archetypes** covering all LangSmith Insights topic clusters (order status, complaints, returns, product research, policies, corporate inquiries, and more)
- **Automatic HITL interrupt handling** (email verification)
- **LLM-generated follow-up questions** matching persona characteristics
- **LangSmith trace tagging** with `archetype_id`, `generation_mode`, `segment`, and `sentiment` for rich Insights filtering
- **GitHub Actions automation** — 6 scheduled runs/day on weekdays, naturally spread across business hours

## Quick Start

### Prerequisites

- Deployed TechHub agent running on LangSmith
- Environment variables set in `.env`:
  - `LANGSMITH_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `LANGGRAPH_DEPLOYMENT_URL`

### Basic Usage

```bash
# Run 1 dynamic conversation (default)
uv run python simulations/run_simulation.py

# Run multiple dynamic conversations
uv run python simulations/run_simulation.py --count 5

# Use static scenarios from scenarios.json (original behavior)
uv run python simulations/run_simulation.py --count 3 --mode static

# Mix static + dynamic
uv run python simulations/run_simulation.py --count 4 --mode mixed

# Test a specific static scenario by ID
uv run python simulations/run_simulation.py --scenario angry_delayed_order

# Override deployment URL
uv run python simulations/run_simulation.py --url https://custom-deployment.langgraph.app
```

## Scenario Modes

### `--mode dynamic` (default)

Generates scenarios on-the-fly by:
1. Querying the SQLite DB for a random real customer + their recent order history
2. Selecting a weighted archetype based on customer segment
3. Calling an LLM to generate a grounded opening query referencing actual orders

Results in infinite variety with realistic, data-grounded conversations.

### `--mode static`

Uses the 10 hardcoded personas in `scenarios.json`. Original behavior, unchanged.

### `--mode mixed`

Splits evenly between static and dynamic scenarios, shuffled together.

## Dynamic Archetypes

12 archetypes covering all LangSmith Insights topic clusters:

| Archetype | Verification Required | Primary Agent | Sentiment Skew |
|---|---|---|---|
| `order_status_check` | Yes | DB/SQL | Mostly neutral |
| `delayed_order_complaint` | Yes | DB/SQL | 90% negative |
| `return_exchange_request` | Yes | DB+Docs | 80% negative |
| `spending_history_review` | Yes | SQL | Mostly neutral |
| `product_research` | No | Docs | Positive/neutral |
| `policy_question` | No | Docs | Positive/neutral |
| `product_spec_deep_dive` | No | Docs | Even split |
| `corporate_bulk_inquiry` | Yes | SQL | Corporate only, mostly neutral |
| `warranty_claim` | Yes | DB+Docs | 75% negative |
| `cancelled_order_confusion` | Yes | DB | 85% negative |
| `home_office_setup` | No | Docs | Home Office weighted |
| `loyalty_inquiry` | Yes | SQL | Even split |

## Static Scenarios (scenarios.json)

For reference, the 10 static scenarios remain available via `--mode static`:

**Requiring email verification**: `power_user_analytics`, `corporate_buyer_bulk`, `order_tracker_simple`, `support_seeker_account_issue`, `multi_order_analysis`, `angry_delayed_order`, `frustrated_wrong_item`

**No verification**: `product_researcher_no_auth`, `policy_question_warranty`, `product_spec_deep_dive`

## GitHub Actions Automation

The workflow in `.github/workflows/simulate_traffic.yml` runs 1 dynamic conversation 6 times per weekday at 2-hour intervals (9am–5:30pm ET), producing naturally spread traffic patterns for LangSmith dashboards.

### Required GitHub Secrets

Add these in **Settings > Secrets and variables > Actions**:

| Secret | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for LLM calls |
| `LANGSMITH_API_KEY` | LangSmith API key for tracing |
| `LANGGRAPH_DEPLOYMENT_URL` | Your LangGraph deployment URL |

### Manual Trigger

From the **Actions** tab → **Simulate TechHub Traffic** → **Run workflow**, you can set `count` and `mode` to run on demand.

## Finding Simulation Traces in LangSmith

### Filter by Simulation Source

```
metadata.source = "automated_simulation"
```

### Filter by Generation Mode

```
metadata.generation_mode = "dynamic"   # LLM+DB generated
metadata.generation_mode = "static"    # From scenarios.json
```

### Filter by Archetype

```
metadata.archetype_id = "delayed_order_complaint"
metadata.archetype_id = "product_research"
```

### Filter by Persona / Sentiment

```
metadata.persona_type = "Corporate"
metadata.sentiment = "negative"
metadata.requires_verification = true
```

## How It Works

### Architecture

1. **Scenario Generation** — Dynamic mode queries DB for real customer + orders, picks weighted archetype, calls LLM to generate opening query. Static mode loads from `scenarios.json`.
2. **Thread Creation** — Creates LangSmith thread with simulation metadata (`archetype_id`, `generation_mode`, `sentiment`, etc.)
3. **Initial Query** — Sends opening query via SDK client
4. **HITL Handling** (if `requires_verification`):
   - Detects `__interrupt__` from agent
   - Auto-generates email response matching persona style
   - Resumes with `Command(resume=email)`
5. **Follow-up Generation** — LLM generates 2-6 realistic follow-up questions based on persona, sentiment, and conversation history
6. **Natural Ending** — Conversation ends when persona is satisfied or max turns reached

## Configuration

Edit `simulations/simulation_config.py` to customize:

```python
DEFAULT_CONVERSATIONS_PER_RUN = 1      # Per GHA run (6 runs/day = 6 conversations)
DEFAULT_SIMULATION_MODE = "dynamic"    # static | dynamic | mixed
MAX_TURNS_PER_CONVERSATION = 8         # Max turns before forced end
SCENARIO_SELECTION = "random"          # random | round_robin | all (static mode only)
```

## Project Structure

```
simulations/
├── __init__.py                    # Package marker
├── run_simulation.py              # Main orchestrator (CLI entry point)
├── dynamic_scenario_generator.py  # DB-grounded LLM scenario generation
├── scenarios.json                 # 10 static customer personas
├── simulation_config.py           # Configuration constants
├── interrupt_handler.py           # HITL interrupt detection/response
└── README.md                      # This file

.github/workflows/
└── simulate_traffic.yml           # Scheduled GitHub Actions automation
```

## Troubleshooting

### Deployment URL Not Found

**Symptoms**: `DEPLOYMENT_URL not set` error

**Solution**: Set `LANGGRAPH_DEPLOYMENT_URL` in `.env` (note: two G's — `LANGGRAPH`, not `LANGRAPH`)

### Interrupt Not Detected

**Symptoms**: HITL scenario doesn't pause for email collection

**Solution**:
- Verify archetype/scenario has `requires_verification: true`
- Check agent classification logic
- Set `LOG_LEVEL = "DEBUG"` in `simulation_config.py`

### Too Many or Too Few Turns

**Solution**: Adjust `MAX_TURNS_PER_CONVERSATION` in `simulation_config.py` or review persona prompts

### Traces Not Appearing in LangSmith

**Solution**: Verify `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGGRAPH_DEPLOYMENT_URL` are set correctly

### Connection Errors

**Solution**: Check deployment status in LangSmith Studio and verify URL is correct

## Success Metrics

- **>95% completion rate** — Very few errors
- **3-5 average turns** — Realistic conversation length
- **100% interrupt handling** — All HITL scenarios successfully resume
- **Archetype variety** — Filter by `metadata.archetype_id` to see distribution across runs
