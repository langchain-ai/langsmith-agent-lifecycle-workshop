"""Connect Module 7 to your LangSmith workspace, or record that you continue without one.

Usage (from the repo root):
    uv run python scripts/module7_connect_langsmith.py                 # asks for your LangSmith API key; the input is hidden
    uv run python scripts/module7_connect_langsmith.py --skip          # continue without a key
    uv run python scripts/module7_connect_langsmith.py --use-env-key   # use the key that is already in .env; asks nothing
    uv run python scripts/module7_connect_langsmith.py --send-live     # send four fresh traces with the key in .env
    uv run python scripts/module7_connect_langsmith.py --check         # has one of the first three been done?

A LangSmith key is optional in Module 7: every lab runs on the seed file. This script is for
people who prefer a prompt to editing `.env`, and it is the first step of the hands-on track.

The script makes a network call only when you give it a key: by typing one at the prompt, or by
passing `--use-env-key` or `--send-live`, which name the key in `.env`. With `--skip`, and when you
press Enter at the prompt, it makes no network call: it checks the seed file, writes the state
file and stops. That holds when `.env` already has a key, for example from Modules 1 to 6: the key
is not read out, not checked and not changed, and nothing is uploaded with it. The script says
that it found one and names `--use-env-key`. Either way the key stays in `.env`, and the notebooks
will use it.

With a key (typed, or `--use-env-key`) it does five things:

1. Reads the key with a hidden prompt, so it never appears on the screen, in the shell history or
   in a coding agent's context.
2. Finds the LangSmith region the key belongs to. A key is valid in one region only and its text
   does not say which, so each cloud region is asked in turn (after the address already in `.env`,
   if there is one). If none accepts the key, you can type the API address of a self-hosted
   LangSmith. A `LANGSMITH_WORKSPACE_ID` in `.env` or in the environment is sent with each of
   these requests, because an organization-scoped key is accepted only together with a workspace
   id. If a region answers that the key needs one and none was sent, the script says so and saves
   nothing: add the line to `.env` and run the script again.
3. Writes `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` and `LANGSMITH_TRACING=true` to `.env`
   (other lines are kept; the file is readable by you only).
4. Uploads the seeded day to your workspace (skip this with `--no-upload`).
5. Prints where to find the traces in LangSmith.

Before the prompt the script says where the upload will go. LangSmith has two kinds of workspace.
In a project-based one (the control at the top left of LangSmith shows the LangSmith logo) the
traces go to the tracing project `techhub-deep-agent-production`. In an agent-based one (that
control shows your workspace name; new LangSmith Cloud organizations are of this kind) traces are
grouped by agent, and what an upload under a bare project name does there is not documented. So
for an agent-based workspace, put `TECHHUB_AGENT_ID=<an agent id>` in `.env` before you give the
script a key (the traces then go to the Production environment of that agent, which is created if
it does not exist), or pass `--no-upload`.

The state file (`.m7_state.json` in the repo root, or the path given with `--state`) is what the
track's Check button reads. Its keys:

    langsmith       "verified" (a key was accepted) or "skipped" (you continue without a key)
    reason          why: "--skip", "no key entered" (Enter at the prompt, or `--use-env-key` with no
                    key in `.env`), "key accepted", "key rejected" or "workspace id needed" (an
                    organization-scoped key without `LANGSMITH_WORKSPACE_ID`)
    seed_verified   true if the seed file is byte-identical to a fresh generation
    seed_sha256     SHA-256 of workshop_modules/module_7/data/techhub_production_day.json
    endpoint        the LangSmith API address in use, or null
    region          its name ("GCP US", "GCP EU", ..., "custom"), or null
    seeded          true if the seeded day is in your workspace
    project         the tracing project the traces go to, or null
    where           the path to the traces in the LangSmith UI, or null
    updated_at      when this file was written (UTC)

The key itself is never printed and never written to the state file.

`--check` asks nothing, changes nothing and makes no network call. It reads the state file and the
seed file and prints one line: `PASS: ...` (exit code 0) when the state file says `verified` or
`skipped` and the seed file still verifies and still has the recorded SHA-256, otherwise
`FAIL: ...` with what to do (exit code 1). A key is never required to pass.

`--send-live` is for after you attached an online evaluator in the LangSmith UI. An evaluator
scores new traces only, and the seeded day is hours old, so this sends four fresh return-window
traces dated now, two of them with the wrong window (`utils.trace_upload.send_live_traces`). It
uses the key and the address in `.env`, asks nothing, calls no model, and changes neither `.env`
nor the state file. Exit code 0 when the four traces were sent, 1 when not (no key in `.env`, or
LangSmith refused).

Exit code of the other forms: 0 when the state file was written and the seed verified; 1 when the
seed file does not verify; 2 when no terminal is available for the hidden prompt (pass `--skip`
or `--use-env-key`, or run the script yourself in a terminal).
"""

import argparse
import getpass
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.monitoring_checks import RESTORE_SEED  # noqa: E402 - how to get the seed file back; one wording for the script and the checker
from utils.trace_seeding import DATA, SEED_FILE, generate_seed, load_seed, seed_files  # noqa: E402

STATE_FILE = REPO_ROOT / ".m7_state.json"
ENV_FILE = REPO_ROOT / ".env"

# LangSmith Cloud regions and their API addresses, from https://docs.langchain.com/langsmith/cloud
# (read 2026-11-19). The default region is asked first.
REGIONS = [
    ("GCP US", "https://api.smith.langchain.com"),
    ("GCP EU", "https://eu.api.smith.langchain.com"),
    ("GCP APAC", "https://apac.api.smith.langchain.com"),
    ("AWS US", "https://aws.api.smith.langchain.com"),
    ("Azure US", "https://azure.api.smith.langchain.com"),
]

SEED_REL = f"workshop_modules/module_7/data/{SEED_FILE}"  # the seed file as messages name it, relative to the repo root
LIVE_TRACES = 4  # what `--send-live` sends: four return-window turns, two of them with the wrong window

PROMPT = "LangSmith API key (input is hidden; press Enter to continue without a key): "
# Printed just before the prompt, where the choice is made.
UPLOAD_NOTICE = (
    "With a key, this script checks it against LangSmith, saves it to {env} and uploads the seeded day of synthetic "
    "traces to that key's workspace. Add --no-upload to save the key without uploading."
)
# Also printed before the prompt, when no agent is named: the only test of the workspace kind that the documentation
# gives is what the control at the top left of LangSmith shows, so the learner has to look before the upload starts.
# Three lines; the terminal wraps each one to its own width.
AGENT_WORKSPACE_NOTICE = (
    "Where the upload goes: the tracing project '{project}'. Before you paste a key, look at the control at the top left of LangSmith:\n"
    "  - It shows the LangSmith logo: your workspace is project-based. Carry on.\n"
    "  - It shows your workspace name: your workspace is agent-based. Traces are grouped by agent there, and what an upload under a bare "
    "project name does is not documented (it may create a new agent of that name). Press Enter now, add the line "
    "TECHHUB_AGENT_ID=<agent id> to {env} (an id of your choice; the traces then go to that agent's Production environment, and the "
    "agent is created if it does not exist), and run this script again. Or run this script with --no-upload."
)
AGENT_NAMED_NOTICE = (
    "Where the upload goes: the {environment} environment of the agent '{agent}' (TECHHUB_AGENT_ID is set, which is the setting for an "
    "agent-based workspace). Add --no-upload to save the key without uploading."
)
# Passed to `Destination.how_to_find`: what to run again after TECHHUB_AGENT_ID was added to .env.
RERUN_WITH_ENV_KEY = "run `uv run python scripts/module7_connect_langsmith.py --use-env-key` again"
ENDPOINT_QUESTION = (
    "No LangSmith Cloud region accepted it. If your LangSmith is self-hosted, type its API address "
    "(for example https://langsmith.example.com/api/v1); otherwise press Enter: "
)


def verify_seed() -> tuple[bool, str | None]:
    """Whether the committed seed file equals a fresh generation, and the file's SHA-256.

    The same comparison as `scripts/module7_seed.py verify`, for the seed file alone: the other
    data files may be absent (the hands-on track removes the answer key from the workshop folder).
    """
    path = DATA / SEED_FILE
    if not path.exists():
        return False, None
    committed = path.read_bytes()
    return committed == seed_files(generate_seed())[SEED_FILE], hashlib.sha256(committed).hexdigest()


def value_in_env_file(path: Path, name: str) -> str | None:
    """The value `.env` gives to `name`, or `None`. A `<placeholder>` and a commented-out line do not count."""
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$", line)
        if match:
            value = match.group(1).split(" #")[0].strip().strip('"').strip("'")
            if value and not value.startswith("<"):
                return value
    return None


def store_in_env_file(path: Path, values: dict[str, str]) -> None:
    """Write `values` to `.env`, replacing earlier lines for the same names and keeping every other line.

    The file is created if it does not exist and is made readable by its owner only.
    """
    names = "|".join(re.escape(name) for name in values)
    assigns = re.compile(rf"\s*(?:export\s+)?(?:{names})\s*=")
    kept = [line for line in path.read_text(encoding="utf-8").splitlines() if not assigns.match(line)] if path.exists() else []
    body = "\n".join(kept + [f"{name}={value}" for name, value in values.items()]) + "\n"
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.chmod(str(path), 0o600)  # the mode above applies only when the file is created


# What one LangSmith address says about a key.
ACCEPTED, NEEDS_WORKSPACE, REJECTED = "accepted", "workspace id needed", "rejected"
# The words by which the SDK's error for an organization-scoped key without a workspace id is recognised
# (`langsmith.utils.LangSmithUserError`, raised for a 403 whose error code is `org_scoped_key_requires_workspace`).
ORG_SCOPED_WORDS = "org-scoped"


def workspace_id_for(env_path: Path) -> str | None:
    """`LANGSMITH_WORKSPACE_ID` as the rest of the script will use it: from the environment, else from `.env`."""
    return (os.environ.get("LANGSMITH_WORKSPACE_ID") or "").strip() or value_in_env_file(env_path, "LANGSMITH_WORKSPACE_ID")


def probe(endpoint: str, secret: str, workspace_id: str | None = None) -> str:
    """What LangSmith at `endpoint` says about the key: `ACCEPTED`, `NEEDS_WORKSPACE` or `REJECTED`. One request.

    The request lists one tracing project, which needs a valid key. (The client's `/info` request
    does not: it answers for any key, so it cannot tell a good key from a bad one.) `workspace_id`
    is sent with it when given: an organization-scoped key is accepted only together with one, and
    without it the SDK raises an error of its own, which is reported as `NEEDS_WORKSPACE`. Nothing
    about the reply is printed.
    """
    from langsmith import utils as ls_utils

    from utils.trace_upload import new_client

    workspace = {"workspace_id": workspace_id} if workspace_id else {}
    try:
        # At most 5 seconds to connect and 15 to answer, so an unreachable region does not stall the prompt.
        client = new_client(api_url=endpoint, api_key=secret, timeout_ms=(5_000, 15_000), **workspace)
        next(iter(client.list_projects(limit=1)), None)
    except ls_utils.LangSmithUserError as exc:
        return NEEDS_WORKSPACE if ORG_SCOPED_WORDS in str(exc) else REJECTED
    except Exception:  # noqa: BLE001 - a wrong region, a rejected key and an unreachable address all mean "no"
        return REJECTED
    return ACCEPTED


def find_endpoint(secret: str, endpoint: str | None, ask, known: str | None = None, workspace_id: str | None = None) -> tuple[str | None, str | None, str]:
    """`(region name, API address, verdict)` for the first address that knows the key, or `(None, None, REJECTED)`.

    `endpoint` (the `--endpoint` flag) is the only address tried when it is given. Otherwise the
    address already in `.env` (`known`) is tried first, then each cloud region, then an address
    the user types. The search stops at the first address that answers `ACCEPTED` or
    `NEEDS_WORKSPACE`: only the region a key belongs to can say that the key needs a workspace id.
    """
    if endpoint:
        verdict = probe(endpoint, secret, workspace_id)
        return ("custom", endpoint.rstrip("/"), verdict) if verdict != REJECTED else (None, None, REJECTED)
    candidates = list(REGIONS)
    if known and known.rstrip("/") not in [address for _, address in REGIONS]:
        candidates.insert(0, ("custom", known.rstrip("/")))
    print("Checking the key against each LangSmith Cloud region...")
    for name, address in candidates:
        verdict = probe(address, secret, workspace_id)
        if verdict != REJECTED:
            return name, address, verdict
    typed = ask(ENDPOINT_QUESTION).strip()
    if typed:
        verdict = probe(typed, secret, workspace_id)
        if verdict != REJECTED:
            return "custom", typed.rstrip("/"), verdict
    return None, None, REJECTED


def destination_notice(env_path: Path) -> str:
    """What to print before a key is given: where the upload will go, and how to tell that it should go elsewhere.

    No request is made for this. Whether a workspace is agent-based cannot be read from a key, so
    the learner is asked to look at LangSmith, before the upload and not after it.
    """
    from utils.trace_seeding import DEFAULT_PROJECT

    def setting(name: str) -> str | None:  # the environment first, then .env: the order in which the upload will read them
        return (os.environ.get(name) or "").strip() or value_in_env_file(env_path, name)

    agent = setting("TECHHUB_AGENT_ID")
    if agent:
        return AGENT_NAMED_NOTICE.format(agent=agent, environment=(setting("TECHHUB_AGENT_ENVIRONMENT") or "production").capitalize())
    return AGENT_WORKSPACE_NOTICE.format(project=setting("M7_PROJECT") or DEFAULT_PROJECT, env=env_path.name)


def use_in_this_process(env_path: Path, values: dict[str, str]) -> None:
    """Make the settings of `.env` visible in this process, with the three new values on top.

    The rest of `.env` matters too: `M7_PROJECT`, `TECHHUB_AGENT_ID` and `LANGSMITH_WORKSPACE_ID`
    decide where the seeded day is uploaded. The LangSmith SDK caches every variable it has read,
    so that cache is cleared.
    """
    from dotenv import load_dotenv
    from langsmith import utils as ls_utils

    load_dotenv(env_path)
    os.environ.update(values)

    if hasattr(ls_utils.get_env_var, "cache_clear"):
        ls_utils.get_env_var.cache_clear()


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {**state, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def check(state_path: Path) -> int:
    """Print one PASS or FAIL line for the setup step and return the exit code (0 or 1). No network, no prompt."""
    how = "Run `uv run python scripts/module7_connect_langsmith.py` in the terminal: paste a LangSmith API key at the hidden prompt, or add --skip to continue without one."
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"FAIL: setup is not recorded yet. {how}")
        return 1
    if not isinstance(state, dict) or state.get("langsmith") not in ("verified", "skipped"):
        print(f"FAIL: setup is not recorded yet. {how}")
        return 1
    seed_ok, seed_sha256 = verify_seed()
    if not seed_ok or state.get("seed_verified") is not True or state.get("seed_sha256") != seed_sha256:
        # RESTORE_SEED names the one file: restoring the whole folder would also bring back files the
        # hands-on track removes on purpose (the answer key).
        print(f"FAIL: the seed file {SEED_REL} is missing or was changed. {RESTORE_SEED}")
        return 1
    print(f"PASS: setup is recorded (LangSmith: {state['langsmith']}) and the seed file is verified.")
    return 0


def send_live(env_path: Path) -> int:
    """`--send-live`: send four fresh return-window traces with the key in `.env`. Returns the exit code (0 sent, 1 not).

    For the moment after an online evaluator was attached in the LangSmith UI: it scores new traces
    only. Asks nothing, calls no model, and changes neither `.env` nor the state file.
    """
    secret = value_in_env_file(env_path, "LANGSMITH_API_KEY")
    if not secret:
        print(f"⏭️  Nothing was sent: {env_path.name} holds no LangSmith key. This step is for learners with a key; without one, carry on.")
        print("   To add a key, run this script without --send-live and paste the key at the hidden prompt.")
        return 1
    settings = {"LANGSMITH_API_KEY": secret}
    known = value_in_env_file(env_path, "LANGSMITH_ENDPOINT")
    if known:
        settings["LANGSMITH_ENDPOINT"] = known
    use_in_this_process(env_path, settings)

    from utils.trace_upload import resolve_destination, send_live_traces

    destination = resolve_destination(True)
    if not destination.available or not send_live_traces("quality", LIVE_TRACES, destination):
        return 1  # the helper has printed its own one-line reason
    print(f"   Find them under: {destination.where} (time range: the last hour is enough).")
    print("   An online evaluator that is attached to this project scores them. How long that takes is not documented: refresh after a minute.")
    return 0


def main(argv: list[str] | None = None, *, prompt=None, ask=input) -> int:
    parser = argparse.ArgumentParser(description="Connect Module 7 to LangSmith, or continue without a key.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--skip", action="store_true", help="continue without a LangSmith key; makes no network call")
    mode.add_argument("--use-env-key", action="store_true", help="use the LangSmith key that is already in .env: check it and upload the seeded day; asks nothing")
    mode.add_argument("--send-live", action="store_true", help="send four fresh traces with the key in .env, for an online evaluator you just attached; asks nothing")
    mode.add_argument("--check", action="store_true", help="print PASS or FAIL for the setup step; asks nothing, changes nothing, no network call")
    parser.add_argument("--state", help="write the state file here instead of .m7_state.json in the repo root")
    parser.add_argument("--env", help="write the settings to this file instead of .env in the repo root")
    parser.add_argument("--endpoint", help="your LangSmith API address, if it is self-hosted; skips the region check")
    parser.add_argument("--no-upload", action="store_true", help="store and check the key, but do not upload the seeded day")
    args = parser.parse_args(argv)
    state_path = Path(args.state) if args.state else STATE_FILE
    env_path = Path(args.env) if args.env else ENV_FILE
    if args.check:
        return check(state_path)
    if args.send_live:
        return send_live(env_path)

    seed_ok, seed_sha256 = verify_seed()
    state = {
        "langsmith": "skipped",
        "reason": "--skip",
        "seed_verified": seed_ok,
        "seed_sha256": seed_sha256,
        "endpoint": None,
        "region": None,
        "seeded": False,
        "project": None,
        "where": None,
    }
    if seed_ok:
        print(f"Seed file verified: {SEED_FILE} is identical to a fresh generation.")
    else:
        print(f"The seed file {SEED_REL} is missing or differs from a fresh generation. {RESTORE_SEED}")

    secret = None
    if args.use_env_key:
        # The one way to use a stored key: asked for by name, so nothing is sent with it by accident.
        secret = value_in_env_file(env_path, "LANGSMITH_API_KEY")
        if secret:
            print(f"Using the LangSmith key that is already in {env_path.name}.")
        else:
            state["reason"] = "no key entered"
            print(f"{env_path.name} holds no LangSmith key, so there is nothing to use. Run this script without --use-env-key to type one.")
    elif not args.skip:
        if prompt is None:
            if not sys.stdin.isatty():
                print("This script needs a terminal for the hidden prompt. Run it yourself in a terminal, or pass --skip.")
                return 2
            prompt = getpass.getpass
        if seed_ok and not args.no_upload:
            print(UPLOAD_NOTICE.format(env=env_path.name))
            print(destination_notice(env_path))
        secret = prompt(PROMPT).strip()
        if not secret:
            # Enter means what the prompt says: no key, no network call. A key that is already in .env is not used.
            state["reason"] = "no key entered"
            if value_in_env_file(env_path, "LANGSMITH_API_KEY"):
                print(
                    f"Nothing typed, so nothing was sent. {env_path.name} already holds a LangSmith key: it was not used and not changed. "
                    "To check that key and upload the seeded day with it, run this script again with --use-env-key."
                )

    if secret:
        # --use-env-key asks nothing, so it does not ask for a self-hosted address either: that comes from .env or --endpoint.
        asker = (lambda question: "") if args.use_env_key else ask
        # The workspace id is read before the key is checked: `.env` is loaded into the process only after a key was
        # accepted, and an organization-scoped key is not accepted without its workspace id.
        workspace_id = workspace_id_for(env_path)
        region, endpoint, verdict = find_endpoint(secret, args.endpoint, asker, known=value_in_env_file(env_path, "LANGSMITH_ENDPOINT"), workspace_id=workspace_id)
        again = "run this script again with --use-env-key" if args.use_env_key else "run this script again"
        if verdict == NEEDS_WORKSPACE:
            state["reason"] = "workspace id needed"
            print(f"⏭️  LangSmith ({region}) knows this key, but it is an organization-scoped key: it works only together with a workspace id. Nothing was saved.")
            if workspace_id:
                print("   A LANGSMITH_WORKSPACE_ID was sent with it and LangSmith still asks for one. Check that it is the id of a workspace, not of the organization.")
            else:
                print(f"   Add the line LANGSMITH_WORKSPACE_ID=<your workspace id> to {env_path.name} (the id of a workspace, not of the organization), then {again}.")
            print("   The labs still run without a LangSmith key.")
        elif endpoint is None:
            state["reason"] = "key rejected"
            print("⏭️  No LangSmith address accepted it, so nothing was saved. The labs still run without a LangSmith key.")
            if args.use_env_key:
                print(f"   The key in {env_path.name} was left as it is. If your LangSmith is self-hosted, pass its API address with --endpoint.")
            else:
                print("   LangSmith API keys start with lsv2_. To try again, run this script again.")
            if workspace_id:
                print("   A LANGSMITH_WORKSPACE_ID was sent with the key. If the key is right, check that id: it must be a workspace this key can use.")
        else:
            settings = {"LANGSMITH_API_KEY": secret, "LANGSMITH_ENDPOINT": endpoint, "LANGSMITH_TRACING": "true"}
            store_in_env_file(env_path, settings)
            use_in_this_process(env_path, settings)
            print(f"LangSmith connected ({region}, {endpoint}). Saved LANGSMITH_API_KEY, LANGSMITH_ENDPOINT and LANGSMITH_TRACING to {env_path.name}.")
            state.update({"langsmith": "verified", "reason": "key accepted", "endpoint": endpoint, "region": region})

            from utils.trace_upload import resolve_destination, upload_seed

            destination = resolve_destination(True)
            if seed_ok and not args.no_upload:
                state["seeded"] = upload_seed(load_seed(), destination)
            state.update({"project": destination.project_name, "where": destination.where})
            print(destination.how_to_find(rerun=RERUN_WITH_ENV_KEY))

    if state["langsmith"] == "skipped":
        print("⏭️  Continuing without a LangSmith key. Every lab runs on the seed file; traces print in the terminal instead of linking to LangSmith.")
    write_state(state_path, state)
    print(f"State written to {state_path.name}: langsmith = {state['langsmith']}, seed_verified = {str(seed_ok).lower()}.")
    return 0 if seed_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
