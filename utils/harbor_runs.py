"""Run Harbor jobs from a notebook and show their results (Module 5 Section 3).

Harbor runs from the managed agent's project (`managed_agent/`), the same command as
`managed_agent/evals/README.md`:

- `--no-project`, so `uv` doesn't rebuild the managed agent's Python 3.14 environment on
  3.12 (that removes the `mda` binary the adapter needs);
- `--env langsmith`, so each trial runs in a LangSmith sandbox instead of local Docker;
- the MDA job plugin (compiles the agent once per job) and the LangSmith plugin (records
  the job as an experiment).

Harbor's own output goes to a log file; the notebook shows a live progress panel instead,
then Harbor's summary table from that log.
"""

import json
import os
import re
import subprocess
import time
import warnings
from pathlib import Path

from IPython.display import Pretty, display
from langsmith import Client

PROJECT = Path(__file__).resolve().parents[1] / "managed_agent"
JOBS = PROJECT / ".mda/evals/jobs"
DATASET = "m5-harbor-techhub-support"  # LangSmith dataset the Harbor plugin records runs in

HARBOR = ["uv", "run", "--no-project", "--python", "3.12", "--with", "harbor[langsmith]==0.21.0", "harbor"]
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")  # terminal colors and cursor codes
# Harbor's progress lines: "<task>__<id>: running agent..."
STAGE = re.compile(r"([\w-]+)__\w+: (running trial|starting environment|running agent|running verifier)")
STAGE_LABEL = {
    "running trial": "queued",
    "starting environment": "starting sandbox, installing agent",
    "running agent": "agent running",
    "running verifier": "verifier running",
}
PROGRESS_LINE = re.compile(r"[⠀-⣿]|\d+/\d+ .*━")  # spinner frames and progress bars


def uv_env() -> dict:
    """The notebook's environment without its virtualenv, so `uv` picks its own."""
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


def mda_runner_ready() -> bool:
    """True once `uv sync --python 3.14` and `uv run mda evals init` have run in managed_agent/."""
    runtime = PROJECT / ".mda/evals/runtime.json"
    return runtime.exists() and Path(json.loads(runtime.read_text())["mda_executable"]).exists()


def _trial_outcomes(job: Path | None) -> dict[str, str]:
    outcomes = {}
    for result_file in job.glob("*__*/result.json") if job else []:
        result = json.loads(result_file.read_text())
        if not result.get("finished_at"):
            continue
        task = result_file.parent.name.split("__")[0]
        if result.get("exception_info"):
            outcomes[task] = "⚠️ harbor_error"
        else:
            reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward", 0)
            outcomes[task] = f"{'✅' if reward else '❌'} reward {reward:g}"
    return outcomes


def _panel(tasks, stages, outcomes, elapsed) -> Pretty:
    done = len(outcomes)
    filled = round(24 * done / len(tasks))
    lines = [f"⏱ {int(elapsed) // 60}:{int(elapsed) % 60:02d}   {'█' * filled}{'░' * (24 - filled)}  {done}/{len(tasks)} tasks done", ""]
    width = max(map(len, tasks))
    for task in tasks:
        lines.append(f"  {task:<{width}}   {outcomes.get(task) or '⏳ ' + stages.get(task, 'waiting')}")
    return Pretty("\n".join(lines))


def harbor_run(tasks: list[str], experiment: str, agent: str = "mda") -> tuple[Path, str]:
    """Run Harbor tasks in LangSmith sandboxes with a live progress panel.

    agent="mda" runs the managed agent through the MDA adapter (the job config in
    evals/harbor-job.json). agent="oracle" runs each task's solution/solve.sh instead:
    no model, a known-good result, to check the task and its verifier.

    Returns (job folder, experiment name). The experiment name gets a timestamp suffix.
    """
    experiment = f"{experiment}-{time.strftime('%Y%m%d-%H%M%S')}"
    argv = [*HARBOR, "run", "--yes", "-p", "evals", "-n", str(len(tasks))]
    for task in tasks:
        argv += ["-i", task]
    if agent == "mda":
        argv += ["--config", "evals/harbor-job.json", "--plugin", "mda_harbor.job_plugin:MDAJobPlugin"]
    else:
        argv += ["-a", agent, "-o", ".mda/evals/jobs"]
    argv += [
        "--env", "langsmith", "--ek", "delete_after_stop_seconds=600",
        "--plugin", "mda_harbor.langsmith_plugin:LangSmithPlugin",
    ]
    env = {
        **uv_env(),
        "PYTHONPATH": ".mda/evals/harbor-adapter",
        "HARBOR_LANGSMITH_DATASET": DATASET,
        "HARBOR_LANGSMITH_EXPERIMENT": experiment,
    }

    before = set(JOBS.iterdir()) if JOBS.exists() else set()
    log_path = PROJECT / f".mda/evals/{experiment}.log"
    stages, outcomes = {}, {}
    started = last_draw = time.time()
    panel = display(_panel(tasks, stages, outcomes, 0), display_id=True)
    with log_path.open("w") as log, subprocess.Popen(
        argv, cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as proc:
        for line in proc.stdout:
            line = ANSI.sub("", line)
            for task, stage in STAGE.findall(line):
                stages[task] = STAGE_LABEL[stage]
            if not PROGRESS_LINE.search(line) and line.strip():
                log.write(line)
            if time.time() - last_draw > 1:  # redraw at most once a second
                new_jobs = set(JOBS.iterdir()) - before if JOBS.exists() else set()
                outcomes = _trial_outcomes(max(new_jobs, key=lambda p: p.name) if new_jobs else None)
                panel.update(_panel(tasks, stages, outcomes, time.time() - started))
                last_draw = time.time()
    new_jobs = set(JOBS.iterdir()) - before if JOBS.exists() else set()
    job = max(new_jobs, key=lambda p: p.name) if new_jobs else None
    panel.update(_panel(tasks, stages, _trial_outcomes(job), time.time() - started))
    if proc.returncode or job is None:
        print("\n".join(log_path.read_text().splitlines()[-40:]))
        raise RuntimeError(f"harbor run exited {proc.returncode}; full log: {log_path}")
    return job, experiment


def harbor_summary(experiment: str) -> None:
    """Print Harbor's own end-of-job tables, as `harbor run` shows them in a terminal."""
    lines = (PROJECT / f".mda/evals/{experiment}.log").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if "┏" in line) - 1  # include the title line
    end = next((i for i, line in enumerate(lines) if line.startswith("Job Info")), len(lines))
    print("\n".join(lines[start:end]).rstrip())


def results_table(experiment: str) -> None:
    """Each task's scores and answer, read back from the LangSmith experiment."""
    client = Client()
    for _ in range(10):  # runs can take a few seconds to become searchable after the job ends
        with warnings.catch_warnings():  # list_runs is deprecated after 2027-01-31 in favor of runs.query
            warnings.simplefilter("ignore", DeprecationWarning)
            runs = sorted(client.list_runs(project_name=experiment, is_root=True), key=lambda r: r.name)
        if runs and all(run.outputs for run in runs):
            break
        time.sleep(3)
    for run in runs:
        outputs = run.outputs or {}
        print(f"▶ {run.name.split('__')[0]}")
        if outputs.get("exception"):
            error = outputs["exception"]
            if isinstance(error, dict):
                error = f"{error.get('exception_type', 'Error')}: {error.get('exception_message', '')}"
            print(f"  ⚠️  harbor_error (infrastructure, not the agent): {str(error)[:300]}")
        rewards = outputs.get("rewards") or {}
        for key in sorted(rewards, key=lambda k: k != "reward"):  # overall reward first
            print(f"  {'✅' if rewards[key] else '❌'} {key}: {rewards[key]:g}")
        answer = (outputs.get("agent_output") or "").strip().replace("\n", " ")
        print("  answer:", answer[:400] or "(no final answer)")
        print()
    print("📊 Experiment:", client.read_project(project_name=experiment).url)
