"""Weekday operations digest: orders stuck in Processing.

Schedules are static declarations. `mda deploy` turns this file into a
LangSmith cron job once the deployment is live. The `context` marks the run as
an ops job so the guard allows the ops-only `get_delayed_orders` tool.
"""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 7 * * 1-5",
    timezone="Europe/London",
    prompt=(
        "Operations digest: use the order-specialist to list orders that have been Processing "
        "for 3 or more days. Summarize the count and the oldest five, and suggest one action."
    ),
    context={"role": "ops"},
)
