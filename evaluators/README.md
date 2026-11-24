# Evaluators

Evaluation functions for measuring agent performance in Module 2. These evaluators are built inline in Module 2, Section 1 and then refactored here for reuse.

## Available Evaluators

| Evaluator | Type | Measures | Returns |
|-----------|------|----------|---------|
| `correctness_evaluator` | Reference-based | Factual accuracy against ground truth | Boolean (True/False) |
| `count_total_tool_calls_evaluator` | Trace-based | Efficiency via tool invocation count | Integer (count) |
| `wrong_return_window_evaluator` | Online code evaluator (Module 7) | Whether a reply gives an opened or used product the 30-day return window | `{"wrong_return_window": True}` when it does, otherwise `False` |

`WRONG_RETURN_WINDOW_SOURCE` is also exported: the source text of `wrong_return_window_evaluator`, ready to paste into LangSmith.

## Usage

### Correctness Evaluator (LLM-as-Judge)

Compares agent output against reference output using an LLM judge:

```python
from evaluators import correctness_evaluator

result = correctness_evaluator(
    inputs={"messages": [{"role": "user", "content": "What's my order status?"}]},
    outputs={"messages": [{"role": "assistant", "content": "Your order shipped"}]},
    reference_outputs={"messages": [{"role": "assistant", "content": "Shipped"}]}
)

# Returns: {"key": "correctness", "score": True, "comment": "reasoning..."}
```

**What it checks:**
- Factual accuracy
- Completeness
- Logical consistency

### Tool Call Counter (Trace-Based)

Counts tool invocations across the entire execution trace:

```python
from evaluators import count_total_tool_calls_evaluator
from langsmith import Client

client = Client()
run = client.read_run(run_id, load_child_runs=True)

result = count_total_tool_calls_evaluator(run)

# Returns: {"key": "total_tool_calls", "score": 7}
```

**What it measures:**
- Execution efficiency
- Number of tool calls (lower is often better)

### Wrong Return Window (Online Code Evaluator)

Used in Module 7, Section 1. The two evaluators above score an experiment against a dataset. This one scores production traces as they arrive, with no reference answer. It lives in `evaluators/online_evaluators.py` as `perform_eval(run, example=None)`, the name and arguments a LangSmith code evaluator must have, and the package exports it as `wrong_return_window_evaluator`.

It takes one run as a plain dictionary (not a `Run` object), reads the customer's message from `run["inputs"]["messages"]` and the reply from the last message of `run["outputs"]["messages"]`, and returns one feedback key:

```python
from evaluators import wrong_return_window_evaluator

run = {
    "inputs": {"messages": [{"role": "user", "content": "I opened my laptop last week. How long do I have to return it?"}]},
    "outputs": {"messages": [{"type": "ai", "content": "You have 30 days from delivery to return your laptop."}]},
}

wrong_return_window_evaluator(run)

# Returns: {"wrong_return_window": True}
```

**What it checks:**
- The customer says the product was opened or used (whole words, so "unopened" and "unused" do not count)
- The reply gives a 30-day window. TechHub's Return Policy gives opened electronics 14 days (`data/documents/policies/return_policy.md`)

**How to read the score:** `True` means a problem was found, so `True` is not a pass. A run without outputs (a failed run) scores `False`; the function never raises.

**Which runs to score:** root runs only (in Module 7, a filter on the run name `deep_support_agent`). A specialist's run inside the trace carries the same question and reply in the same `messages` shape, so without the filter one wrong answer is scored more than once.

**Limits:** it is a wording heuristic and calls no model. A reply that mentions both windows, or a customer who describes an opened product in other words, is outside what it can judge.

**Attaching it in LangSmith:** print `WRONG_RETURN_WINDOW_SOURCE` and paste it into a Code Evaluator. The LangSmith docs give the path as **Evaluators** tab > **+ Evaluator** > **Code Evaluator** under **Create from scratch**; Module 7, Section 1 walks through the steps for both workspace types. The function imports nothing and uses no helper outside its own body, because LangSmith runs the pasted text on its own.

```python
from evaluators import WRONG_RETURN_WINDOW_SOURCE

print(WRONG_RETURN_WINDOW_SOURCE)
```

## Using in Experiments

The correctness evaluator and the tool call counter work with LangSmith's `evaluate()` function:

```python
from langsmith import Client
from evaluators import correctness_evaluator, count_total_tool_calls_evaluator

client = Client()

results = client.evaluate(
    target_function,
    data="your-dataset-name",
    evaluators=[
        correctness_evaluator,
        count_total_tool_calls_evaluator
    ],
    experiment_prefix="my-experiment"
)
```

## Evaluator Signatures

LangSmith automatically routes evaluators based on their function signature:

**Reference-based** (compares outputs to ground truth):
```python
def evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    # Has access to example data and expected outputs
    pass
```

**Trace-based** (analyzes execution metadata):
```python
from langsmith.schemas import Run

def evaluator(run: Run) -> dict:
    # Has access to full execution trace
    pass
```

You can mix both types in a single experiment.

**Online code evaluator** (scores one production run; attached in LangSmith, not passed to `evaluate()`):
```python
def perform_eval(run: dict, example=None) -> dict:
    # `run` is a dictionary in LangSmith's run data format; return {feedback_key: score}
    pass
```

`wrong_return_window_evaluator` has this signature. The `example=None` argument is needed because LangSmith passes a second argument when the evaluator is tested against a dataset example.

## Module 2 Learning Path

**Section 1**: Build evaluators inline to understand evaluation concepts

**Section 2**: Import these pre-built evaluators to focus on eval-driven development workflow

See the notebooks for detailed explanations of evaluation principles and best practices.
