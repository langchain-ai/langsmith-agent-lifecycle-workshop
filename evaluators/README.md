# Evaluators

Evaluation functions for measuring agent performance in Module 2. These evaluators are built inline in Module 2, Section 1 and then refactored here for reuse.

## Available Evaluators

| Evaluator | Type | Measures | Returns |
|-----------|------|----------|---------|
| `correctness_evaluator` | Reference-based | Factual accuracy against ground truth | Boolean (True/False) |
| `count_total_tool_calls_evaluator` | Trace-based | Efficiency via tool invocation count | Integer (count) |

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

## Using in Experiments

Both evaluators work with LangSmith's `evaluate()` function:

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

## Module 2 Learning Path

**Section 1**: Build evaluators inline to understand evaluation concepts

**Section 2**: Import these pre-built evaluators to focus on eval-driven development workflow

See the notebooks for detailed explanations of evaluation principles and best practices.
