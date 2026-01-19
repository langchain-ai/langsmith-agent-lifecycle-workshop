# TechHub Agent Simulation System

Automated system for generating realistic customer support traces for demo and testing purposes against the deployed `supervisor_hitl_sql_agent`.

## Overview

This simulation system creates realistic multi-turn conversations with the deployed TechHub agent using:
- **10 customer personas** (2 negative sentiment, 2 positive, 6 neutral)
- **Automatic HITL interrupt handling** (email verification)
- **LLM-generated follow-up questions** matching persona characteristics
- **LangSmith trace tagging** for easy filtering

## Quick Start

### Prerequisites

- Deployed TechHub agent running on LangSmith
- Environment variables set (already in your `.env`):
  - `LANGSMITH_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `LANGSMITH_PROJECT=langsmith-agent-lifecycle-workshop-deployment`

### Basic Usage

```bash
# Run default simulation (7 random scenarios)
uv run python simulations/run_simulation.py

# Run custom number of conversations
uv run python simulations/run_simulation.py --count 10

# Test specific scenario
uv run python simulations/run_simulation.py --scenario angry_delayed_order

# Override deployment URL (default is already set to live deployment)
uv run python simulations/run_simulation.py --url https://custom-deployment.langgraph.app
```

## Available Scenarios

### Scenarios Requiring Email Verification (8)

1. **power_user_analytics** - Analytics query about spending patterns (Priya Patel, neutral)
2. **corporate_buyer_bulk** - Corporate bulk purchase inquiry (Jonathan Taylor, neutral)
3. **order_tracker_simple** - Simple order status check (Sarah Chen, positive)
4. **support_seeker_account_issue** - Account history for taxes (Daniel Park, neutral)
5. **multi_order_analysis** - Complete purchase history review (Jamal Washington, positive)
6. **angry_delayed_order** - Frustrated about delayed order (Michael Rodriguez, **negative**)
7. **frustrated_wrong_item** - Angry about wrong product received (Lisa Martinez, **negative**)

### Scenarios Without Verification (2)

8. **product_researcher_no_auth** - Product comparison (anonymous, neutral)
9. **policy_question_warranty** - Return policy inquiry (anonymous, neutral)
10. **product_spec_deep_dive** - Technical specs question (anonymous, positive)

## Scenario Distribution

- **Email verification required**: 8 scenarios (80%)
- **No verification**: 2 scenarios (20%)
- **SQL/DB agent usage**: 6 scenarios
- **Docs agent usage**: 4 scenarios
- **Sentiment breakdown**: 6 neutral, 2 positive, 2 negative

The **2 negative sentiment personas** are designed to trigger your online sentiment evaluator.

## Finding Simulation Traces in LangSmith

### Filter by Simulation Source

1. Navigate to LangSmith → Projects → `langsmith-agent-lifecycle-workshop-deployment`
2. Apply filter: `metadata.source = "automated_simulation"`
3. All simulation traces will be displayed

### Filter by Specific Scenarios

```
metadata.scenario_id = "angry_delayed_order"  # Negative sentiment
metadata.scenario_id = "power_user_analytics"  # Analytics query
```

### Filter by Persona Type

```
metadata.persona_type = "Consumer"  # Consumer segment
metadata.persona_type = "Corporate"  # Corporate buyer
metadata.sentiment = "negative"     # Negative sentiment only
```

### Filter by Verification Requirement

```
metadata.requires_verification = true   # HITL scenarios only
metadata.requires_verification = false  # Non-HITL scenarios
```

## How It Works

### Architecture

1. **Scenario Selection** - Randomly selects N scenarios from `scenarios.json`
2. **Thread Creation** - Creates new LangSmith thread with simulation metadata
3. **Initial Query** - Sends persona's initial query via SDK client
4. **HITL Handling** (if required):
   - Detects `__interrupt__` from agent
   - Auto-generates email response matching persona style
   - Resumes with `Command(resume=email)`
5. **Follow-up Generation** - LLM generates 2-6 realistic follow-up questions based on:
   - Persona description
   - Communication style
   - Sentiment (negative personas stay frustrated)
   - Conversation history
6. **Natural Ending** - Conversation ends when persona is satisfied or max turns reached

### Negative Sentiment Behavior

The **angry_delayed_order** and **frustrated_wrong_item** personas:
- Use CAPS and exclamation marks
- Express frustration/impatience
- Demand immediate resolution
- May grudgingly accept after 3-4 turns but still express disappointment
- Designed to trigger negative sentiment evaluators

## Configuration

Edit `simulations/simulation_config.py` to customize:

```python
DEFAULT_CONVERSATIONS_PER_RUN = 7      # Change default count
MAX_TURNS_PER_CONVERSATION = 8         # Max turns before forced end
SIMULATION_MODEL = "anthropic:claude-sonnet-4"  # Model for persona simulation
SCENARIO_SELECTION = "random"          # random | round_robin | all
```

## Adding New Scenarios

1. Edit `simulations/scenarios.json`
2. Add new scenario following this structure:

```json
{
  "scenario_id": "new_scenario",
  "customer": {
    "email": "customer@email.com",
    "customer_id": "CUST-XXX",
    "segment": "Consumer"
  },
  "persona": {
    "description": "Detailed persona description",
    "communication_style": "How they communicate",
    "sentiment": "neutral",  // or "positive" or "negative"
    "typical_queries": ["query type 1", "query type 2"]
  },
  "initial_query": "The first message they send",
  "requires_verification": true,  // or false
  "tags": ["tag1", "tag2"]
}
```

3. Update `metadata.total_scenarios` count
4. Test locally before running at scale

## Troubleshooting

### Interrupt Not Detected

**Symptoms**: HITL scenario doesn't pause for email collection

**Possible Causes**:
- Scenario has `requires_verification: false` (check `scenarios.json`)
- Customer email doesn't exist in database
- Agent didn't classify as requiring verification

**Solution**:
- Verify scenario configuration
- Check agent's classification logic
- Review interrupt_handler logs (set `LOG_LEVEL = "DEBUG"`)

### Too Many or Too Few Turns

**Symptoms**: Conversations always hit max turns or end too quickly

**Possible Causes**:
- Persona prompt not generating appropriate endings
- `MAX_TURNS_PER_CONVERSATION` too high/low
- Sentiment instructions not matching persona

**Solution**:
- Adjust `MAX_TURNS_PER_CONVERSATION` in `simulation_config.py`
- Review persona descriptions in `scenarios.json`
- Check follow-up prompt logic in `run_simulation.py`

### Traces Not Appearing in LangSmith

**Symptoms**: No simulation traces in LangSmith project

**Possible Causes**:
- `LANGSMITH_API_KEY` not set
- `LANGSMITH_PROJECT` doesn't match deployment project
- Deployment URL incorrect

**Solution**:
- Verify environment variables: `echo $LANGSMITH_API_KEY`
- Check project name matches: `langsmith-agent-lifecycle-workshop-deployment`
- Verify deployment URL in logs
- Review GitHub Actions logs for errors (if using automation)

### Sentiment Evaluator Not Triggering

**Symptoms**: Negative personas don't trigger sentiment evaluator

**Possible Causes**:
- Evaluator not configured on deployment
- Metadata not passed correctly
- Persona not using sufficiently negative language

**Solution**:
- Verify online evaluator is active in LangSmith
- Check trace metadata includes `sentiment: "negative"`
- Review conversation transcript - ensure CAPS, exclamation marks present
- May need 1-2 minutes for evaluator to run (check Feedback tab)

### Connection Errors

**Symptoms**: "Connection refused" or timeout errors

**Possible Causes**:
- Deployment URL incorrect
- Deployment not running
- Network issues

**Solution**:
- Verify deployment URL: `https://langsmith-agent-lifecycle-w-564445430b575a46895dfccb4b48bd26.us.langgraph.app`
- Check deployment status in LangSmith UI
- Test deployment manually first via LangSmith Studio

## Development

### Project Structure

```
simulations/
├── __init__.py              # Package marker
├── run_simulation.py        # Main orchestrator (CLI entry point)
├── scenarios.json           # 10 customer personas
├── simulation_config.py     # Configuration constants
├── interrupt_handler.py     # HITL interrupt detection/response
└── README.md                # This file
```

### Testing Individual Components

```python
# Test interrupt handler
from simulations.interrupt_handler import InterruptHandler
handler = InterruptHandler()
response = handler.generate_email_response(
    interrupt_msg="Please provide email",
    customer_email="test@example.com",
    persona={"communication_style": "casual", "sentiment": "neutral"}
)
print(response)  # "It's test@example.com"
```

### Running with Debug Logging

```bash
# Edit simulation_config.py: LOG_LEVEL = "DEBUG"
uv run python simulations/run_simulation.py --scenario order_tracker_simple --count 1
```

## Success Metrics

When running simulations, you should see:

- **>95% completion rate** - Very few errors
- **3-5 average turns** - Realistic conversation length
- **100% interrupt handling** - All HITL scenarios successfully resume
- **Metadata filtering works** - Easy to find simulation traces in LangSmith
- **Negative personas trigger evaluator** - Check Feedback tab after 1-2 minutes

## Future Enhancements

Potential improvements (not in current implementation):

- Scenario versioning and rotation
- Evaluation metrics for simulation quality
- Dashboard for simulation statistics
- More edge case scenarios (multiple items, complex returns, etc.)
- Integration with online evaluators for automated quality checks
- Scheduled automation via GitHub Actions or cron

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs with `LOG_LEVEL = "DEBUG"`
3. Test individual scenarios first before batch runs
4. Verify deployment is accessible via LangSmith Studio
