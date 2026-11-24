"""Check a Module 7 exercise from the command line.

    uv run python workshop_modules/module_7/exercises/check.py s1_evaluator
    uv run python workshop_modules/module_7/exercises/check.py s2_report s2_claim s3_triage
    uv run python workshop_modules/module_7/exercises/check.py --list
    uv run python workshop_modules/module_7/exercises/check.py --restore-data

Prints one line per id, "PASS: ..." or "FAIL: ..." with what is wrong, and exits with 0 when
every check passes, 1 when one fails and 2 for an id it does not know.

`--restore-data` is for a check that says a data file is missing or was changed: it regenerates
the files of `workshop_modules/module_7/data/` that differ from what the module's generator
writes (the seed, its labels, the sample report, the sample issue board). It leaves the exercise
files alone and writes `answers.json` only where that file already exists.

    id             file in this folder          function
    setup          (none: reads the state file that scripts/module7_connect_langsmith.py writes)
    s1_evaluator   return_window_evaluator.py   perform_eval(run, example=None)
    s2_report      read_the_report.py           summarise(report)
    s2_claim       read_the_report.py           flagged_in_subcategory(name, seed, labels, perform_eval)
    s3_triage      triage.py                    next_action(issue)
    s4_masking     masking.py                   build_anonymizer()

The exercise files are read from the folder named in the environment variable M7_EXERCISES_DIR,
or from this folder when it is not set. No check calls a model, LangSmith or the network, and
none needs an API key. All the logic is in `utils/monitoring_checks.py`, which the notebooks and
the unit tests use as well.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))  # the repository root, so that `utils` can be imported from any working directory

from utils.monitoring_checks import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], default_folder=HERE))
