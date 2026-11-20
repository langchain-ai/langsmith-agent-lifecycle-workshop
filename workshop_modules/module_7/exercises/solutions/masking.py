"""Reference solution for `exercises/masking.py` (Module 7, Section 4).

Check it from the repository root:

    M7_EXERCISES_DIR=workshop_modules/module_7/exercises/solutions uv run python workshop_modules/module_7/exercises/check.py s4_masking
"""

import re

from langsmith.anonymizer import create_anonymizer

# Something@domain.tld. Deliberately simple: it is a mask for traces, not an address validator.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def build_anonymizer():
    """Return an anonymizer that replaces every email address with `<email>` and leaves other text alone."""
    # The client applies the rule to every string in a run's inputs, outputs, metadata and error.
    return create_anonymizer([{"pattern": EMAIL, "replace": "<email>"}])
