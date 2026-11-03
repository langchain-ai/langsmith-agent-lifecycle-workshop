"""Verifier: opened-item return window from the Return Policy (see ../Task.md)."""

import re
import sys

sys.path.insert(0, "/tests")
from mda_result import final_answer, load_messages, report  # noqa: E402

answer = final_answer(load_messages()).lower().replace("\u2019", "'")  # curly apostrophes

names_14_days = bool(re.search(r"\b14[- ]?days?\b|\bfourteen days\b", answer))
not_eligible = bool(
    re.search(r"not eligible|isn't eligible|ineligible|outside|past the|beyond|no longer|can't be returned|cannot be returned|unfortunately", answer)
)
# Only an answer that opens with "yes" grants the standard return; "if it's defective, you can
# still return it" is a valid alternative route and must not fail.
wrongly_allows = answer.lstrip("*#> _-").startswith("yes")
mentions_defect_route = bool(re.search(r"defect|warranty", answer))

report(
    {
        "names the 14-day opened-item window": names_14_days,
        "says the item is not eligible": not_eligible,
        "does not say the return is allowed": not wrongly_allows,
    },
    reward_keys=["names the 14-day opened-item window", "says the item is not eligible", "does not say the return is allowed"],
    stats={"mentions defect or warranty route": mentions_defect_route},
)
