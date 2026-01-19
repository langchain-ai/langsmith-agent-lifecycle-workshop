"""Configuration for simulation system."""

import sys
from pathlib import Path
from typing import Literal

# Add parent directory to path to import from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DEFAULT_MODEL

# Simulation Parameters
DEFAULT_CONVERSATIONS_PER_RUN = 7  # 5-10 range, default to middle
MAX_TURNS_PER_CONVERSATION = 8     # Prevent runaway conversations
SIMULATION_MODEL = DEFAULT_MODEL  # Use same model as rest of project

# Deployment Settings
DEPLOYMENT_GRAPH_NAME = "supervisor_hitl_sql_agent"

# Default deployment URL (can be overridden via --url CLI arg)
DEFAULT_DEPLOYMENT_URL = "https://langsmith-agent-lifecycle-w-564445430b575a46895dfccb4b48bd26.us.langgraph.app"

# Scenario Selection Strategy
SCENARIO_SELECTION: Literal["random", "round_robin", "all"] = "random"
# - "random": Pick N random scenarios per run (with replacement)
# - "round_robin": Cycle through scenarios sequentially
# - "all": Run all scenarios every time (ignores conversation count)

# Paths
SIMULATION_DIR = Path(__file__).parent
SCENARIOS_FILE = SIMULATION_DIR / "scenarios.json"
RESULTS_DIR = SIMULATION_DIR / "results"  # Optional: save conversation logs

# LangSmith Tagging
SIMULATION_METADATA = {
    "source": "automated_simulation",
    "system": "techhub_demo_generator",
    "environment": "production"
}

# Interrupt Handling
EMAIL_COLLECTION_TIMEOUT = 30  # seconds before giving up on interrupt
MAX_VERIFICATION_RETRIES = 2   # How many times to retry email if fails

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
