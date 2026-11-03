"""Managed LangSmith sandbox declaration.

MDA owns the run-scoped name, reuse across turns, and lifecycle. Delete this
directory to run without a sandbox.

To provision a recipe snapshot, add ``sandbox/setup.sh``. ``mda deploy`` and
``mda dev`` run it once and save the result as a snapshot; new threads clone it
without re-running the script.
"""

from managed_deepagents import define_sandbox

# Egress allowlist (default-deny). The sandbox only reads the TechHub docs and
# catalog saved in the snapshot, so the only hosts it needs are the ones
# setup.sh uses: PyPI for packages and GitHub's tarball host for the docs.
# Ports are pinned to 443, which also blocks raw TCP (SSH, databases) everywhere.
# An organization on restricted egress applies its own allowlist instead.
# See https://docs.langchain.com/langsmith/sandbox-auth-proxy
EGRESS_ALLOW_LIST = [
    "pypi.org:443",
    "files.pythonhosted.org:443",
    "codeload.github.com:443",
]

sandbox = define_sandbox(
    # Reclaim idle sandboxes after 10 minutes.
    idle_ttl_seconds=600,
    # Default per-command timeout, in seconds.
    default_timeout=600,
    proxy_config={"access_control": {"allow_list": EGRESS_ALLOW_LIST}},
)
