def perform_eval(run, example=None):
    """Flag a reply that gives an opened or used product the 30-day return window.

    TechHub's Return Policy: unopened electronics can be returned within 30 days of delivery,
    opened electronics within 14 days.

    Returns {"wrong_return_window": True} when the customer says the product was opened or
    used and the agent's reply gives a 30-day window, otherwise {"wrong_return_window": False}.
    True means a problem was found.
    """

    def as_message(message):
        # A message is a dictionary. A serialized LangChain message keeps its fields under "kwargs".
        if not isinstance(message, dict):
            return {}
        inner = message.get("kwargs")
        return inner if isinstance(inner, dict) else message

    def text_of(message):
        # Content is a string, or a list of content blocks such as {"type": "text", "text": "..."}.
        content = as_message(message).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [block if isinstance(block, str) else block.get("text", "") for block in content if isinstance(block, (str, dict))]
            return " ".join(part for part in parts if isinstance(part, str))
        return ""

    def words_of(text):
        # Lower-case words, split at everything that is not a letter or a digit. Whole words
        # matter: "unopened" and "unused" must not count as "opened" and "used".
        return "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()

    def messages_of(payload):
        # run["outputs"] is None or {} when the run failed, so a missing key is normal.
        messages = payload.get("messages") if isinstance(payload, dict) else None
        return messages if isinstance(messages, list) else []

    if not isinstance(run, dict):
        return {"wrong_return_window": False}
    asked = messages_of(run.get("inputs"))
    answered = messages_of(run.get("outputs"))
    if not asked or not answered:
        return {"wrong_return_window": False}

    # The customer's message is the last one in the inputs. The reply is the last message in the
    # outputs, and only if the agent wrote it: a turn can also end on a tool call or an error.
    question = words_of(text_of(asked[-1]))
    last = as_message(answered[-1])
    if last.get("type", last.get("role")) not in ("ai", "assistant"):
        return {"wrong_return_window": False}
    reply = words_of(text_of(last))

    says_opened = "opened" in question or "used" in question
    gives_30_days = any(a in ("30", "thirty") and b in ("day", "days") for a, b in zip(reply, reply[1:]))
    return {"wrong_return_window": says_opened and gives_30_days}
