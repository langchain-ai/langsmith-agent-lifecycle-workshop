"""Run the Module 7 notebooks top to bottom with no LangSmith key and no network, and check their answers.

Usage (from the repo root; `env -i` removes any credentials the shell exports):

    env -i PATH="$PATH" HOME="$HOME" LANGSMITH_TRACING=false .venv/bin/python scripts/verify_module7_offline.py [notebook ...]
    env -i PATH="$PATH" HOME="$HOME" LANGSMITH_TRACING=false .venv/bin/python scripts/verify_module7_offline.py --placeholder-key [notebook ...]

With no notebook named, the four notebooks in `workshop_modules/module_7/` are checked. For each one:

1. The notebook is copied to a new scratch folder, and the executed copy is saved there. The file you
   named is never changed.
2. It runs with `nbclient` in a kernel whose environment holds only `PATH`, `HOME` and
   `LANGSMITH_TRACING=false`, whatever the calling shell exports. The working directory is
   `workshop_modules/module_7/`, where a learner opens the notebooks, so relative paths behave the same.
3. A `sitecustomize.py` on the kernel's `PYTHONPATH` guards the network. Loopback addresses and Unix
   sockets pass, because the Jupyter kernel needs them. Every other `connect` and every name lookup of
   another host is written to a log file and refused. Subprocesses the notebook starts inherit the guard.
4. The run passes when no cell raised, the log is empty, and the output holds every "✅ Verified" line
   expected for that notebook. The expected lines come from `answers.json` through
   `utils.monitoring_checks.expected_line`, so they are the lines a passed `check(...)` prints.

`--placeholder-key` runs every notebook a second time with `LANGSMITH_API_KEY="<langsmith-api-key>"`
(the `.env.example` placeholder) and `LANGSMITH_TRACING=true`, and also fails if any output contains
"Failed to" (the start of the SDK's upload-failure log lines).

Options:
    --checks ID,ID     the checker ids to expect, for a notebook whose file name is not one of the four
    --keep DIR         put the scratch folders under DIR instead of a new temporary folder
    --timeout SECONDS  time limit per cell (default 300)

Exit code 0 when every run passes, 1 when one fails, 2 for a usage error. No model or LangSmith call
is made: the notebooks of Module 7 call neither on the default path, and the guard refuses any attempt.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO / "workshop_modules" / "module_7"
sys.path.insert(0, str(REPO))

# The checker ids whose "✅ Verified" line each notebook must print (PRD section 6.6).
EXPECTED_CHECKS = {
    "section_1_online_evals_and_alerts.ipynb": ["s1_signals", "s1_evaluator", "s1_filter_sample", "s1_alert", "s1_routing"],
    "section_2_insights.ipynb": ["s2_report", "s2_claim"],
    "section_3_engine.ipynb": ["s3_evidence", "s3_triage", "s3_assertions"],
    "section_4_gateway_and_governance.ipynb": ["s4_leak", "s4_masking", "s4_routes", "s4_blocks"],
}

PLACEHOLDER_KEY = "<langsmith-api-key>"
KERNEL_NAME = "python3"  # the kernelspec name the Module 4 to 7 builders write into every notebook

SITECUSTOMIZE = '''
"""Network guard installed by scripts/verify_module7_offline.py. Not part of the workshop."""
import os
import socket

_LOG = os.environ.get("M7_SOCKET_LOG")
_LOCAL_NAMES = ("localhost", "::1", "0.0.0.0", "")


def _host(value):
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    return "" if value is None else str(value)


def _is_local(address):
    if isinstance(address, (str, bytes)):  # a Unix socket path
        return True
    host = _host(address[0]) if isinstance(address, tuple) and address else ""
    return host in _LOCAL_NAMES or host.startswith("127.") or host.startswith("::ffff:127.")


def _record(kind, target):
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as log:
            log.write(f"pid {os.getpid()} {kind} {target!r}\\n")


_connect, _connect_ex, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo


def connect(self, address):
    if _is_local(address):
        return _connect(self, address)
    _record("connect", address)
    raise ConnectionRefusedError(f"refused by the Module 7 offline guard: {address!r}")


def connect_ex(self, address):
    if _is_local(address):
        return _connect_ex(self, address)
    _record("connect", address)
    raise ConnectionRefusedError(f"refused by the Module 7 offline guard: {address!r}")


def getaddrinfo(host, *args, **kwargs):
    if host is None or _is_local((host,)):
        return _getaddrinfo(host, *args, **kwargs)
    _record("lookup", _host(host))
    raise socket.gaierror(socket.EAI_NONAME, f"refused by the Module 7 offline guard: name lookup of {_host(host)}")


socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
'''


def _kernel_spec_dir(scratch: Path) -> Path:
    """A kernelspec named like the notebooks' one that starts this interpreter, so the kernel is the repo's venv."""
    folder = scratch / "kernels" / KERNEL_NAME
    folder.mkdir(parents=True, exist_ok=True)
    spec = {
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Python 3 (ipykernel)",
        "language": "python",
    }
    (folder / "kernel.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    return folder.parent


def _kernel_env(guard_dir: Path, log: Path, placeholder_key: bool) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(guard_dir)),
        "LANGSMITH_TRACING": "false",
        "PYTHONPATH": str(guard_dir),
        "M7_SOCKET_LOG": str(log),
        "PYDEVD_DISABLE_FILE_VALIDATION": "1",  # silences a debugger warning of ipykernel on stderr
    }
    if placeholder_key:
        env.update(LANGSMITH_API_KEY=PLACEHOLDER_KEY, LANGSMITH_TRACING="true")
    return env


def _output_text(nb) -> str:
    """Everything the notebook printed or displayed, and every error, as one string."""
    parts: list[str] = []
    for cell in nb.cells:
        for output in cell.get("outputs", []):
            kind = output.get("output_type")
            if kind == "stream":
                parts.append(output.get("text", ""))
            elif kind in ("execute_result", "display_data"):
                parts.append(str(output.get("data", {}).get("text/plain", "")))
            elif kind == "error":
                parts.append(f"{output.get('ename')}: {output.get('evalue')}")
                parts.extend(output.get("traceback", []))
    return "\n".join(parts)


def _failed_cell(nb) -> tuple[int, str] | None:
    for index, cell in enumerate(nb.cells):
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                return index, f"{output.get('ename')}: {output.get('evalue')}"
    return None


def run_one(notebook: Path, checks: list[str], scratch_root: Path, *, placeholder_key: bool, timeout: int) -> bool:
    """Execute one notebook copy and check it. Prints one result line (and the reasons on failure)."""
    import nbformat
    from jupyter_client.kernelspec import KernelSpecManager
    from jupyter_client.manager import AsyncKernelManager
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError, CellTimeoutError

    from utils.monitoring_checks import expected_line

    mode = "placeholder key" if placeholder_key else "no key"
    scratch = Path(tempfile.mkdtemp(prefix=f"{notebook.stem}-", dir=scratch_root))
    guard_dir = scratch / "guard"
    guard_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text(SITECUSTOMIZE.lstrip(), encoding="utf-8")
    log = scratch / "non_local_connects.log"
    log.touch()
    copy = scratch / notebook.name
    shutil.copyfile(notebook, copy)

    nb = nbformat.read(copy, as_version=4)
    specs = KernelSpecManager(kernel_dirs=[str(_kernel_spec_dir(scratch))])
    km = AsyncKernelManager(kernel_name=KERNEL_NAME, kernel_spec_manager=specs)
    client = NotebookClient(nb, km=km, timeout=timeout, kernel_name=KERNEL_NAME, resources={"metadata": {"path": str(MODULE_DIR)}})

    problems: list[str] = []
    try:
        client.execute(env=_kernel_env(guard_dir, log, placeholder_key))
    except (CellExecutionError, CellTimeoutError) as exc:
        failed = _failed_cell(nb)
        where = f"cell {failed[0]}: {failed[1]}" if failed else str(exc).strip().splitlines()[-1]
        problems.append(f"a cell raised ({where})")
    except Exception as exc:  # noqa: BLE001 - a kernel that does not start is a failed run, not a crash of this script
        problems.append(f"the notebook could not be executed ({type(exc).__name__}: {exc})")
    nbformat.write(nb, copy)

    text = _output_text(nb)
    attempts = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    if attempts:
        problems.append(f"{len(attempts)} non-loopback connection attempts, first: {attempts[0]}")
    missing = [check_id for check_id in checks if expected_line(check_id) not in text]
    if missing:
        problems.append("no verified line for " + ", ".join(missing))
    if placeholder_key and "Failed to" in text:
        problems.append("an output contains 'Failed to'")

    found = len(checks) - len(missing)
    summary = f"{notebook.name} ({mode}): {len(nb.cells)} cells, {len(attempts)} non-loopback connects, {found} of {len(checks)} verified lines"
    if problems:
        print(f"FAIL {summary}")
        for problem in problems:
            print(f"     - {problem}")
    else:
        print(f"PASS {summary}")
    print(f"     executed copy: {copy}")
    return not problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Module 7 notebooks offline and check their verified lines.")
    parser.add_argument("notebooks", nargs="*", type=Path, help="notebooks to run (default: the four in workshop_modules/module_7)")
    parser.add_argument("--placeholder-key", action="store_true", help="also run with the .env.example placeholder key and tracing on")
    parser.add_argument("--checks", help="comma-separated checker ids to expect (default: from the notebook's file name)")
    parser.add_argument("--keep", type=Path, help="folder for the scratch copies (default: a new temporary folder)")
    parser.add_argument("--timeout", type=int, default=300, help="time limit per cell in seconds (default 300)")
    args = parser.parse_args(argv)

    notebooks = [path.resolve() for path in args.notebooks] or [MODULE_DIR / name for name in EXPECTED_CHECKS if (MODULE_DIR / name).exists()]
    if not notebooks:
        print(f"No notebook given and none found in {MODULE_DIR.relative_to(REPO)}. Build them first, or name one.")
        return 2
    plan = []
    for notebook in notebooks:
        if not notebook.is_file():
            print(f"No such notebook: {notebook}")
            return 2
        if args.checks is not None:  # `--checks ""` expects no verified line (a notebook without checks)
            checks = [item.strip() for item in args.checks.split(",") if item.strip()]
        elif notebook.name in EXPECTED_CHECKS:
            checks = EXPECTED_CHECKS[notebook.name]
        else:
            print(f"{notebook.name} is not one of the four Module 7 notebooks: pass --checks with its checker ids.")
            return 2
        plan.append((notebook, checks))

    scratch_root = args.keep.resolve() if args.keep else Path(tempfile.mkdtemp(prefix="m7-verify-"))
    scratch_root.mkdir(parents=True, exist_ok=True)
    modes = [False, True] if args.placeholder_key else [False]
    results = [run_one(notebook, checks, scratch_root, placeholder_key=mode, timeout=args.timeout) for mode in modes for notebook, checks in plan]
    print(f"{sum(results)} of {len(results)} runs passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
