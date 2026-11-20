"""Exercise for Module 7, Section 4: keep a customer's email address out of the traces you upload.

The support agent already runs `PIIMiddleware`, which redacts email addresses before the model sees
them. The trace is a separate copy: the root run's input, the middleware's own spans and the raw
model output are uploaded as they were. Run the check from the repository root before you change
anything, and it tells you how many uploaded payloads still contain the address:

    uv run python workshop_modules/module_7/exercises/check.py s4_masking

Then fill in `build_anonymizer` below and run the check again. The check traces one turn of a
model-free agent into a local recorder, so nothing is sent anywhere and no key is needed.

The check runs this file's imports, assignments, definitions and blocks (`if`, `for`, `try`, `with`).
It does not run a bare call at the top level of the file (a `print`, a test call), so whatever
`build_anonymizer` needs belongs in one of those, or inside the function.
"""


def build_anonymizer():
    """Return an anonymizer that masks email addresses in everything a LangSmith client uploads.

    An anonymizer is a function that the LangSmith client applies to the inputs, outputs, metadata
    and error of every run just before it uploads them: `Client(anonymizer=build_anonymizer())`.
    `langsmith.anonymizer.create_anonymizer` builds one from a list of rules; a rule is a dictionary
    {"pattern": <a regular expression>, "replace": <the text to put in its place>}.

    The check passes when, in the local capture:

    - no uploaded payload contains an email address (the customer's, or any other), and
    - text that is not an email address is uploaded unchanged: the order id in the same message
      must survive. Hiding everything does not pass.
    """
    raise NotImplementedError("build_anonymizer is not written yet: workshop_modules/module_7/exercises/masking.py")
