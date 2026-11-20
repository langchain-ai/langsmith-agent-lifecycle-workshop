"""Print the saved Insights report and the saved Engine issue board of Module 7.

    uv run python workshop_modules/module_7/exercises/show_report.py

This is the reading version of Sections 2 and 3 for a short session: read the report top down
(key points, categories, subcategories, highlighted traces), then the three issues. Both files are
hand-built samples generated from the module's seed, not output of LangSmith Insights or Engine;
their structure follows the documented API shapes. To look at a trace that the report or an issue
mentions, print it as a tree with its trace key (here t-0042, an ordinary order lookup):

    uv run python -c "from utils.trace_seeding import load_seed, print_trace; print_trace(load_seed(), 't-0042')"

The output fits the terminal it runs in: every line is wrapped to the terminal's width, between 60
and 100 columns, and to 80 columns when the output is not a terminal (piped to a file, or run by a
coding agent). In a terminal narrower than 87 columns the category table puts the numbers of each
row on a second line. It is about 120 lines long at 100 columns and longer when narrower, so make
the terminal panel taller or scroll back to the top.

One thing the board file holds is not printed: the assertions of the offline example that issue 1
proposes. Choosing them is an exercise of Section 3, so the script only says that the example exists.

No key, no network, no model.
"""

import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # the repository root

from utils.trace_seeding import SEVERITY_LABELS, load_engine_issues, load_insights_report, load_seed  # noqa: E402

MAX_WIDTH = 100  # wider lines are harder to read than to wrap
MIN_WIDTH = 60  # the two-line table rows need 59 columns; a narrower terminal wraps the lines itself
PIPED_WIDTH = 80  # used when the output is not a terminal
TABLE_WIDTH = 87  # what the one-line-per-row category table needs


def page_width() -> int:
    """The line width to print at: the terminal's width, kept between `MIN_WIDTH` and `MAX_WIDTH`.

    `shutil.get_terminal_size` reads the environment variable `COLUMNS`, then asks the terminal.
    When neither answers (the output is piped), the width is `PIPED_WIDTH`.
    """
    columns = shutil.get_terminal_size(fallback=(PIPED_WIDTH, 24)).columns
    return max(MIN_WIDTH, min(MAX_WIDTH, columns))


def wrap(text: str, width: int, indent: str = "  ", bullet: str = "") -> str:
    """Wrap `text` to `width`. With `bullet`, the first line starts with it and the others line up under the text.

    A line never ends inside a hyphenated name: a branch such as `engine/normalise-order-ids` and a
    tool or agent name stay in one piece, so they can be read and copied.
    """
    return textwrap.fill(text, width=width, initial_indent=indent + bullet, subsequent_indent=indent + " " * len(bullet), break_on_hyphens=False)


def banner(title: str, width: int) -> None:
    print("=" * width)
    print(wrap(title, width, indent=""))
    print("=" * width)


def when(timestamp: str) -> str:
    return f"{datetime.fromisoformat(timestamp.replace('Z', '+00:00')):%Y-%m-%d %H:%M} UTC"


def table_row(cluster: dict, total: int, indent: str, width: int) -> str:
    """One category or subcategory: one line when the page is wide enough for the table, else the name and a line of numbers."""
    stats = cluster.get("stats") or {}
    runs, share = cluster["num_runs"], 100 * cluster["num_runs"] / total
    errors, latency, cost = 100 * stats.get("error_rate", 0.0), stats.get("latency_p50", 0.0), stats.get("cost_p50", 0.0)
    if width >= TABLE_WIDTH:
        return f"  {indent + cluster['name']:<38} {runs:>5} {share:>5.1f}% {errors:>9.1f}% {latency:>10.1f}s {cost:>10.4f}"
    return f"  {indent}{cluster['name']}\n  {indent}  {runs:>3} convs  {share:>5.1f}%  errors {errors:>5.1f}%  p50 {latency:>5.1f}s  ${cost:.4f}"


def show_report(report: dict, width: int) -> None:
    summary = report["report"]
    # A top-level category has no parent. The `level` number is documented for subcategories only.
    categories = sorted((c for c in report["clusters"] if c["parent_id"] is None), key=lambda c: -c["num_runs"])
    total = sum(c["num_runs"] for c in categories)

    banner("INSIGHTS REPORT (hand-built sample generated from the seed, not real Insights output)", width)
    print(wrap(summary["title"], width, indent=""))
    print(wrap(f"Status: {report['status']}. Finished {when(report['end_time'])}. {total} conversations in {len(categories)} categories.", width, indent=""))

    print("\nKey points")
    for number, point in enumerate(summary["key_points"], start=1):
        print(wrap(point, width, bullet=f"{number}. "))

    print("\nCategories and subcategories")
    print(wrap("convs: conversations. share: of all conversations. error rate (errors): share of conversations with an errored run. "
               "p50: the median, of latency and of cost in $.", width))
    if width >= TABLE_WIDTH:
        print(f"  {'':<38} {'convs':>5} {'share':>6} {'error rate':>10} {'latency p50':>11} {'cost p50 $':>10}")
    for category in categories:
        print(table_row(category, total, "", width))
        children = sorted((c for c in report["clusters"] if c["parent_id"] == category["id"]), key=lambda c: -c["num_runs"])
        for child in children:
            print(table_row(child, total, "  ", width))

    print("\nHighlighted traces")
    for trace in sorted(summary["highlighted_traces"], key=lambda t: t["rank"]):
        print(wrap(trace.get("cluster_name", ""), width, bullet=f"{trace['rank']}. "))
        print(wrap(trace["highlight_reason"], width, indent="     "))
        if trace.get("summary"):
            print(wrap(trace["summary"], width, indent="     "))


def show_issues(board: dict, width: int) -> None:
    issues = sorted(board["issues"], key=lambda issue: issue["severity"])
    print()
    banner("ENGINE ISSUE BOARD (hand-built sample generated from the seed, not real Engine output)", width)
    for number, issue in enumerate(issues, start=1):
        print()
        print(wrap(f"[{SEVERITY_LABELS[issue['severity']]}] {issue['status']}: {issue['name']}", width, indent="", bullet=f"Issue {number}  "))
        fixes = issue.get("fixes") or []
        pull_requests = ", ".join(f"pull request {fix['pr_number']} on branch {fix['branch']}" for fix in fixes) or "none"
        print(wrap(f"type: {issue.get('type', 'actionable')}   tags: {', '.join(issue.get('tags') or [])}", width))
        print(wrap(f"fixes: {pull_requests}", width))
        print(wrap(f"first seen {when(issue['first_seen_at'])}, last seen {when(issue['last_seen_at'])}", width))
        if issue.get("watching_since"):
            print(wrap(f"watched since {when(issue['watching_since'])}; new traces since then: {issue.get('recurrences_since_watching', 0)}", width))
        print("  Description")
        print(wrap(issue["description"], width, indent="    "))
        if issue.get("proposed_fix"):
            print("  Proposed fix")
            print(wrap(issue["proposed_fix"], width, indent="    "))
        evidence = board.get("evidence", {}).get(issue["id"], [])
        if evidence:
            print("  Evidence")
            for item in evidence:
                print(wrap(f"{item['seed_trace_key']}: {item['comment']}", width, indent="    ", bullet="- "))
        # The assertions of a proposed example are not printed: picking them is the exercise `s3_assertions` of Section 3.
        for example in board.get("offline_examples", {}).get(issue["id"], []):
            count = len(example.get("assertions") or [])
            print("  Proposed offline example")
            print(wrap(
                f"Built from trace {example['seed_trace_key']}, with {count} {'assertion' if count == 1 else 'assertions'}: short claims "
                "that a correct answer must satisfy. They are not listed here, because choosing them is an exercise of Section 3.",
                width, indent="    "))


def main(width: int | None = None) -> int:
    width = width or page_width()
    seed = load_seed()  # shifts the day so that the newest trace is 5 minutes old; the two files follow it
    show_report(load_insights_report(seed), width)
    show_issues(load_engine_issues(seed), width)
    print()
    print(wrap("Next: fill in read_the_report.py and triage.py in this folder, then run check.py s2_report s2_claim s3_triage.", width, indent=""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
