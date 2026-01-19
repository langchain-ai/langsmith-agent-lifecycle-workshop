#!/usr/bin/env python3
"""
Main simulation script for generating continuous TechHub agent traces.

Usage:
    uv run python simulations/run_simulation.py

    # Override conversation count
    uv run python simulations/run_simulation.py --count 10

    # Run specific scenario
    uv run python simulations/run_simulation.py --scenario power_user_analytics

    # Override deployment URL (though default is already set)
    uv run python simulations/run_simulation.py --url https://custom-deployment.langgraph.app
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from langgraph_sdk import get_client
from langgraph_sdk.schema import Command
from langchain.chat_models import init_chat_model

# Add parent directory to path to import from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulations.simulation_config import (
    DEFAULT_CONVERSATIONS_PER_RUN,
    DEFAULT_DEPLOYMENT_URL,
    DEPLOYMENT_GRAPH_NAME,
    MAX_TURNS_PER_CONVERSATION,
    SCENARIOS_FILE,
    SCENARIO_SELECTION,
    SIMULATION_METADATA,
    SIMULATION_MODEL,
    LOG_LEVEL,
    LOG_FORMAT,
)
from simulations.interrupt_handler import InterruptHandler

# Setup
load_dotenv()
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


class SimulationRunner:
    """Orchestrates multi-turn simulations against deployed agent."""

    def __init__(self, deployment_url: str):
        self.sdk_client = get_client(url=deployment_url)
        self.interrupt_handler = InterruptHandler()
        self.llm = init_chat_model(SIMULATION_MODEL)
        self.stats = {
            "total_runs": 0,
            "successful": 0,
            "failed": 0,
            "total_turns": 0,
            "interrupts_handled": 0
        }

    def load_scenarios(self) -> List[Dict]:
        """Load scenario definitions from JSON."""
        with open(SCENARIOS_FILE) as f:
            data = json.load(f)
        return data["scenarios"]

    def select_scenarios(self, scenarios: List[Dict], count: int) -> List[Dict]:
        """Select scenarios based on strategy."""
        if SCENARIO_SELECTION == "all":
            return scenarios
        elif SCENARIO_SELECTION == "random":
            return random.choices(scenarios, k=count)
        elif SCENARIO_SELECTION == "round_robin":
            # Simple round-robin: cycle through sequentially
            # For production, could track state in a file
            start_idx = self.stats["total_runs"] % len(scenarios)
            selected = []
            for i in range(count):
                idx = (start_idx + i) % len(scenarios)
                selected.append(scenarios[idx])
            return selected
        else:
            # Default to random
            return random.choices(scenarios, k=count)

    async def run_scenario(self, scenario: Dict) -> Dict:
        """
        Execute a single scenario conversation.

        Returns:
            Dict with run_id, thread_id, turn_count, success status
        """
        scenario_id = scenario['scenario_id']
        logger.info(f"Starting scenario: {scenario_id}")

        # Create thread with simulation metadata
        customer_segment = scenario.get("customer", {}).get("segment", "anonymous") if scenario.get("customer") else "anonymous"
        thread = await self.sdk_client.threads.create(
            metadata={
                **SIMULATION_METADATA,
                "scenario_id": scenario_id,
                "persona_type": customer_segment,
                "requires_verification": scenario["requires_verification"],
                "sentiment": scenario["persona"].get("sentiment", "neutral")
            }
        )
        thread_id = thread["thread_id"]

        try:
            if scenario["requires_verification"]:
                # Hybrid approach: SDK for interrupts, then custom follow-ups
                result = await self._run_hitl_scenario(thread_id, scenario)
            else:
                # Standard approach (no interrupts)
                result = await self._run_standard_scenario(thread_id, scenario)

            self.stats["successful"] += 1
            logger.info(f"Scenario {scenario_id} completed successfully: {result['turn_count']} turns")
            return result

        except Exception as e:
            logger.error(f"Scenario {scenario_id} failed: {e}", exc_info=True)
            self.stats["failed"] += 1
            return {"success": False, "error": str(e), "scenario_id": scenario_id}

    async def _run_hitl_scenario(self, thread_id: str, scenario: Dict) -> Dict:
        """
        Handle scenario requiring email verification.

        Flow:
            1. Send initial query
            2. Detect interrupt (email collection)
            3. Auto-provide email from scenario customer data
            4. Resume with Command(resume=email)
            5. Continue with follow-up conversation
        """
        customer = scenario["customer"]
        initial_query = scenario["initial_query"]

        # Step 1: Initial message
        logger.debug(f"Sending initial query: {initial_query}")
        input_msg = {"messages": [{"role": "user", "content": initial_query}]}
        result = await self.sdk_client.runs.wait(
            thread_id,
            DEPLOYMENT_GRAPH_NAME,
            input=input_msg
        )

        turn_count = 1

        # Step 2: Check for interrupt
        if self.interrupt_handler.is_interrupt_present(result):
            logger.info(f"Interrupt detected for {customer['email']}")
            self.stats["interrupts_handled"] += 1

            # Step 3: Extract what the agent is asking for
            interrupt_msg = self.interrupt_handler.extract_interrupt_value(result)
            logger.debug(f"Interrupt message: {interrupt_msg}")

            # Step 4: Auto-provide email based on persona
            email_response = self.interrupt_handler.generate_email_response(
                interrupt_msg=interrupt_msg,
                customer_email=customer["email"],
                persona=scenario["persona"]
            )

            # Step 5: Resume with email
            logger.debug(f"Resuming with email response: {email_response}")
            result = await self.sdk_client.runs.wait(
                thread_id,
                DEPLOYMENT_GRAPH_NAME,
                command=Command(resume=email_response)
            )
            turn_count += 1

        # Step 6: Continue with follow-up turns
        additional_turns = await self._run_followup_turns(
            thread_id=thread_id,
            scenario=scenario,
            initial_response=result
        )

        return {
            "success": True,
            "thread_id": thread_id,
            "turn_count": turn_count + additional_turns,
            "customer_verified": True,
            "scenario_id": scenario["scenario_id"]
        }

    async def _run_standard_scenario(self, thread_id: str, scenario: Dict) -> Dict:
        """
        Handle scenario without verification (product/policy queries).

        Simpler flow - no interrupts expected.
        """
        initial_query = scenario["initial_query"]

        logger.debug(f"Sending initial query: {initial_query}")
        input_msg = {"messages": [{"role": "user", "content": initial_query}]}
        result = await self.sdk_client.runs.wait(
            thread_id,
            DEPLOYMENT_GRAPH_NAME,
            input=input_msg
        )

        # Continue conversation with follow-ups
        additional_turns = await self._run_followup_turns(
            thread_id=thread_id,
            scenario=scenario,
            initial_response=result
        )

        return {
            "success": True,
            "thread_id": thread_id,
            "turn_count": 1 + additional_turns,
            "customer_verified": False,
            "scenario_id": scenario["scenario_id"]
        }

    async def _run_followup_turns(
        self,
        thread_id: str,
        scenario: Dict,
        initial_response: Dict
    ) -> int:
        """
        Generate and execute follow-up queries based on persona.

        Uses LLM to generate realistic follow-up questions based on:
        - Persona description
        - Agent's previous response
        - Typical query patterns
        - Sentiment (negative personas remain frustrated)

        Returns:
            Number of additional turns executed
        """
        turn_count = 0
        persona = scenario["persona"]
        sentiment = persona.get("sentiment", "neutral")

        # Build conversation history
        conversation_history = [
            {"role": "user", "content": scenario["initial_query"]},
            {"role": "assistant", "content": initial_response["messages"][-1]["content"]}
        ]

        # Determine target number of turns based on scenario complexity
        # Negative sentiment tends to have more back-and-forth
        min_turns = 2 if sentiment == "negative" else 1
        max_turns = min(MAX_TURNS_PER_CONVERSATION - 1, 6)

        for turn in range(max_turns):
            # Generate follow-up query using persona
            followup_prompt = self._build_followup_prompt(
                persona=persona,
                conversation_history=conversation_history,
                turn_number=turn + 2,  # +2 because we already had initial query
                min_turns=min_turns
            )

            followup_query = await self.llm.ainvoke(followup_prompt)
            followup_content = followup_query.content.strip()

            # Check if persona decides to end conversation
            if self._should_end_conversation(followup_content):
                logger.debug(f"Conversation naturally concluded at turn {turn_count + 1}")
                break

            # Send follow-up
            logger.debug(f"Sending follow-up query (turn {turn + 2}): {followup_content}")
            input_msg = {"messages": [{"role": "user", "content": followup_content}]}
            result = await self.sdk_client.runs.wait(
                thread_id,
                DEPLOYMENT_GRAPH_NAME,
                input=input_msg
            )

            turn_count += 1
            conversation_history.extend([
                {"role": "user", "content": followup_content},
                {"role": "assistant", "content": result["messages"][-1]["content"]}
            ])

            self.stats["total_turns"] += 1

        return turn_count

    def _build_followup_prompt(
        self,
        persona: Dict,
        conversation_history: List[Dict],
        turn_number: int,
        min_turns: int = 1
    ) -> str:
        """Build prompt for generating realistic follow-up query."""
        sentiment = persona.get("sentiment", "neutral")

        # Sentiment-specific instructions
        sentiment_instructions = {
            "negative": """
- Remain frustrated and impatient throughout the conversation
- Use caps, exclamation marks, and demanding language
- Express disappointment or frustration even if the agent is helpful
- Don't become fully satisfied easily - press for faster resolution
- After 3-4 turns, you might grudgingly accept the resolution but still express frustration""",
            "positive": """
- Be appreciative when the agent provides helpful information
- Thank the agent for their help
- Express satisfaction when your needs are met
- After 2-3 helpful exchanges, thank them and end naturally""",
            "neutral": """
- Be professional and straightforward
- Ask clarifying questions if needed
- End naturally after getting sufficient information"""
        }

        return f"""You are simulating a customer with this profile:

Description: {persona['description']}
Communication Style: {persona['communication_style']}
Sentiment: {sentiment}
Typical Queries: {', '.join(persona['typical_queries'])}

Sentiment-Specific Behavior:
{sentiment_instructions.get(sentiment, sentiment_instructions['neutral'])}

Conversation so far:
{self._format_history(conversation_history)}

This is turn {turn_number} of the conversation. Generate the next natural follow-up question or statement this customer would make, or respond with "CONVERSATION_END" if the customer would be satisfied and end the conversation.

Requirements:
- Stay in character (communication style, tone, sentiment)
- Ask relevant follow-ups based on agent's response
- Be realistic (don't ask everything at once)
- Minimum turns before ending: {min_turns} (don't end before this)
- After {turn_number} turns, lean toward ending naturally if needs are met
- If satisfied with the answer, express thanks (appropriate to sentiment) and include CONVERSATION_END
- Do NOT break character - maintain sentiment throughout

Your response (just the customer's message, or CONVERSATION_END):"""

    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history for prompt."""
        lines = []
        for msg in history:
            role = "Customer" if msg["role"] == "user" else "Agent"
            content = msg["content"][:500]  # Truncate long messages
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _should_end_conversation(self, query: str) -> bool:
        """Check if query indicates conversation should end."""
        query_lower = query.lower()
        end_signals = [
            "conversation_end",
            "conversation end",
            "end conversation",
            # Don't rely solely on phrases as they might be part of content
        ]
        # Check for explicit end signal
        return any(signal in query_lower for signal in end_signals)

    async def run_all(self, count: int) -> None:
        """Main entry point: run N simulations."""
        scenarios = self.load_scenarios()
        selected = self.select_scenarios(scenarios, count)

        logger.info(f"Starting {len(selected)} simulation runs")
        logger.info(f"Deployment: {DEPLOYMENT_GRAPH_NAME}")

        results = []
        for scenario in selected:
            result = await self.run_scenario(scenario)
            results.append(result)
            self.stats["total_runs"] += 1

            # Small delay between scenarios to avoid overwhelming the deployment
            await asyncio.sleep(1)

        self._log_summary()

        # Exit with error code if any failed
        if self.stats["failed"] > 0:
            logger.error(f"{self.stats['failed']} scenarios failed")
            sys.exit(1)

    def _log_summary(self) -> None:
        """Log final statistics."""
        logger.info("=" * 60)
        logger.info("SIMULATION COMPLETE")
        logger.info(f"Total Runs: {self.stats['total_runs']}")
        logger.info(f"Successful: {self.stats['successful']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Total Turns: {self.stats['total_turns']}")
        logger.info(f"Interrupts Handled: {self.stats['interrupts_handled']}")
        avg_turns = self.stats['total_turns'] / max(self.stats['successful'], 1)
        logger.info(f"Avg Turns per Conversation: {avg_turns:.1f}")
        logger.info("=" * 60)


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run TechHub agent simulations")
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_CONVERSATIONS_PER_RUN,
        help=f"Number of conversations to simulate (default: {DEFAULT_CONVERSATIONS_PER_RUN})"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Run specific scenario by ID (e.g., 'angry_delayed_order')"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_DEPLOYMENT_URL,
        help=f"Deployment URL (default: {DEFAULT_DEPLOYMENT_URL})"
    )

    args = parser.parse_args()

    if not args.url:
        logger.error("DEPLOYMENT_URL not set. Provide via --url or check DEFAULT_DEPLOYMENT_URL in config.")
        sys.exit(1)

    logger.info(f"Connecting to deployment: {args.url}")
    runner = SimulationRunner(deployment_url=args.url)

    if args.scenario:
        # Run single scenario
        scenarios = runner.load_scenarios()
        scenario = next((s for s in scenarios if s["scenario_id"] == args.scenario), None)
        if not scenario:
            logger.error(f"Scenario '{args.scenario}' not found")
            logger.info(f"Available scenarios: {[s['scenario_id'] for s in scenarios]}")
            sys.exit(1)
        result = await runner.run_scenario(scenario)
        runner._log_summary()
        if not result.get("success", False):
            sys.exit(1)
    else:
        # Run batch
        await runner.run_all(args.count)


if __name__ == "__main__":
    asyncio.run(main())
