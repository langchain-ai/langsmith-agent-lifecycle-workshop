"""Build Module 5 notebooks (Evals 201) for the TechHub workshop.

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module5.py workshop_modules/module_5
"""

import sys
from pathlib import Path

import nbformat as nbf

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
KERNEL = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}


def md(s):
    return nbf.v4.new_markdown_cell(s.strip("\n"))


def code(s):
    return nbf.v4.new_code_cell(s.strip("\n"))


def save(name, cells):
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    for i, cell in enumerate(cells):  # stable ids, so regenerating gives a clean diff
        cell["id"] = f"cell-{i:03d}"
    nb.metadata["kernelspec"] = KERNEL
    nbf.write(nb, OUT / name)
    print("wrote", OUT / name, len(cells), "cells")


# Section 2 shows an excerpt of query_my_orders as a colored markdown code block (like
# modular-workshops' verifier excerpt). The lines are copied from tools/database.py at build
# time, so the excerpt can't drift; a missing anchor fails the build.
DATABASE_PY = (Path(__file__).resolve().parents[2] / "tools/database.py").read_text().splitlines()


def source_lines(start: str, end: str | None = None) -> list[str]:
    """Lines of tools/database.py from the first line starting with `start` to the next starting with `end`."""
    starts = [n for n, line in enumerate(DATABASE_PY) if line.startswith(start)]
    if not starts:
        raise ValueError(f"tools/database.py has no line starting with {start!r}: update the Section 2 excerpt")
    i = starts[0]
    if end is None:
        return DATABASE_PY[i : i + 1]
    ends = [n for n in range(i, len(DATABASE_PY)) if DATABASE_PY[n].startswith(end)]
    if not ends:
        raise ValueError(f"tools/database.py has no line starting with {end!r} after {start!r}")
    return DATABASE_PY[i : ends[0] + 1]


_def = source_lines("def query_my_orders(")
assert DATABASE_PY[DATABASE_PY.index(_def[0]) - 1] == "@tool", "query_my_orders is no longer a @tool"
QUERY_MY_ORDERS_EXCERPT = "\n".join([
    *source_lines("_SCOPED_VIEWS = {", "}"),
    "# _scoped_authorizer (not shown) allows reads of these views and the public products table only",
    "",
    "",
    "@tool",
    *_def,
    source_lines('    """Run one read-only SQL SELECT')[0] + ' ..."""',
    *source_lines("    context = runtime.context", "        cursor = conn.execute(query)"),
    "        ...  # fetch at most _MAX_ROWS rows and format them",
])


# Shared by Sections 1 and 2: the deep agent takes a verified customer ID from run context
# (as an app does after sign-in), so the target function looks the customer up from the
# email in the question. Mirrors Module 2's target function otherwise.
TARGET_FUNCTION = r'''
import re
import sqlite3
import uuid
from pathlib import Path

from config import DEFAULT_DB_PATH

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def customer_id_for(question: str) -> str | None:
    """Look up the customer the way sign-in would: by the email they gave."""
    match = EMAIL.search(question)
    if not match:
        return None
    with sqlite3.connect(f"{Path(DEFAULT_DB_PATH).resolve().as_uri()}?mode=ro", uri=True) as conn:
        row = conn.execute("SELECT customer_id FROM customers WHERE email = ?", (match.group(0),)).fetchone()
    return row[0] if row else None


def target_function(inputs: dict) -> dict:
    """Target function that runs our agent to get outputs for evaluation."""

    thread_id = uuid.uuid4()
    config = {"configurable": {"thread_id": thread_id}}
    question = inputs["messages"][-1]["content"]

    result = AGENT.invoke(
        inputs,
        config=config,
        context=SupportContext(customer_id=customer_id_for(question)),
    )

    return {
        "messages": [{"role": "assistant", "content": result["messages"][-1].text}]
    }
'''

# ============================================================================
# SECTION 1: Baseline evaluation (mirrors module_2/section_1_baseline_evaluation.ipynb;
# see docs/2026-11-12-module-5-sections-1-2-prd.md)
# ============================================================================
s1 = [
    md('''
# Module 5, Section 1: Establishing Baseline with Offline Evaluation

In Module 4 we built a TechHub customer support agent on the Deep Agents harness: a main agent that delegates order questions to an order specialist and product and policy questions to a product-policy specialist. But before we can put it in front of customers, we first need to build up confidence that it does the things we expect it to do.

Throughout this module, we'll learn how to run offline evaluations to establish baseline performance and then systematically improve our agent with evaluation-driven development (EDD).

**What is offline evaluation?**

Evaluation is a crucial, ongoing process that allows us to quantitatively measure how well our application is working, identify areas for improvement, and reliably evolve our system over time.

<div align="center">
    <img src="../../images/offline_eval_process.png">
</div>

The offline evaluation process is comprised of a few components:

1. Dataset - a curated set of representative examples, where each example includes:
    - an input to the system
    - a ground truth (reference) output that demonstrates what the expected, high quality outcome should look like
2. Application - the LLM system that we intend to evaluate. We feed it our example inputs, and collect the system's actual output.
3. Evaluators - functions that quantify some aspect of performance by comparing the inputs, outputs, and reference outputs


**What makes a good eval setup?**

When beginning to create a new eval suite, it's often best to:

- Gather a small set of labeled examples that are representative of your system's core functionality and scenarios it should handle.
- Lean on domain expertise to ensure the examples are representative and accurate.
- Select only a few, simple metrics. In practice, binary evaluation metrics force clearer thinking, more consistent labeling, and are easier/faster to interpret when analyzing and iterating on your system.

Starting with a large sample and/or many, complex metrics makes it harder to inspect and deeply understand system behavior, which quickly leads to analysis paralysis.

Let's see how we can perform offline evaluation on our TechHub deep agent in LangSmith to establish the baseline performance!
'''),
    md('''
#### Setup

You need a `.env` with model access (see [Model access](../../README.md#model-access-direct-keys-or-the-llm-gateway) in the README) and the document vectorstore, which the product-policy specialist searches: `uv run python data/data_generation/build_vectorstore.py` (one-time, about 60 seconds).
'''),
    code('''
import os
import warnings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=r".*is deprecated and will be removed after", category=DeprecationWarning)
'''),
    md('''
## 1. Curate a set of representative examples

In our use case, we've teamed up with the TechHub customer support team to create 13 ground truth examples. Each example has:

- **inputs**: A customer's question
- **outputs**: The expected correct answer (i.e. ground truth)
- **metadata**: A category that the customer support team uses to bucket question types

The last example asks about an order that belongs to a different customer. The correct answer is a refusal, which lets us check that the agent never shares another customer's data.

This dataset structure allows us to evaluate the "end-to-end" nature of our agent - commonly referred to as [final answer evaluation](https://docs.langchain.com/langsmith/evaluation-approaches#evaluating-an-agent%E2%80%99s-final-response).

<div align="center">
    <img src="../../images/final-response-eval.png" width="800">
</div>

Let's load and explore the dataset:
'''),
    code('''
import json
from pathlib import Path
from pprint import pprint

# Load the dataset from JSON
dataset_path = Path("baseline_dataset.json")

with open(dataset_path, "r") as f:
    examples = json.load(f)
'''),
    code('''
pprint(examples[0])
'''),
    md('''
## 2. Create a dataset in LangSmith

Note that we convert the examples into `messages` format so that it's natively stored in LangSmith with the structure needed to use these examples when invoking our agent.
'''),
    code('''
import uuid
from langsmith import Client

client = Client()

dataset_name = f"techhub-deep-agent-baseline-{uuid.uuid4()}"
dataset_description = "Representative set of customer support questions and answers curated by our support team"

dataset = client.create_dataset(
    dataset_name=dataset_name,
    description=dataset_description,
)

client.create_examples(
    dataset_id=dataset.id,
    inputs=[
        {"messages": [{"role": "user", "content": ex["inputs"]["question"]}]}
        for ex in examples
    ],
    outputs=[
        {"messages": [{"role": "assistant", "content": ex["outputs"]["answer"]}]}
        for ex in examples
    ],
    metadata=[ex["metadata"] for ex in examples],
)

print(f"Created dataset: {dataset_name}")
print(f"📊 {dataset.url}")
'''),
    md('''
## 3. Initialize the agent we want to evaluate

Here we'll use the deep support agent we built in Module 4:

<div align="center">
    <img src="../../images/deep_support_agent.svg" width="900">
</div>

The agent takes the customer's identity from **run context** (`SupportContext(customer_id=...)`), set by the app after sign-in, never from the conversation. The customer-scope guard only lets order tools return that customer's data.
'''),
    code('''
from agents.deep_support_agent import SupportContext, create_deep_support_agent

agent = create_deep_support_agent()
'''),
    md('''
Quick test:
'''),
    code('''
import uuid

thread_id = uuid.uuid4()
config = {"configurable": {"thread_id": thread_id}}

t = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "What's your return policy for opened electronics?",
            }
        ]
    },
    config=config,
    context=SupportContext(),
)
'''),
    code('''
t["messages"][-1].pretty_print()
'''),
    md('''
## 4. Define our evaluators

Evaluators are functions that score how well your application performs on a particular example.

We'll start out with three simple evaluators: `correctness`, `total_tool_calls`, and `order_specialist_tool_calls`
'''),
    md('''
### Evaluator #1: Correctness

An evaluator that uses LLM-as-a-Judge to determine if the agent's output is "correct" when comparing it against the reference output (i.e. ground truth output).

> Note: We manually define the LLM-as-a-Judge evaluator below for clarity, but you can achieve the same goal with fewer lines of code via our [openevals](https://github.com/langchain-ai/openevals) library.
'''),
    code('''
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from config import DEFAULT_MODEL


CORRECTNESS_PROMPT = """You are an expert data labeler evaluating model outputs for correctness.

Your task is to assign a boolean score based on the following rubric:

<Rubric>
  A correct answer (True):
  - Provides accurate and complete information
  - Contains no factual errors
  - Addresses all parts of the question
  - Is logically consistent
</Rubric>

<Instructions>
  - Carefully read the input and output
  - Compare the output to the reference_output
  - Check for factual accuracy and completeness
  - Focus on correctness of information rather than style or verbosity differences
  - Return a boolean score (True if correct, False if incorrect), not a string
</Instructions>

<Note>
- It's ok if the ouput provides additional information that is not directly included in the reference output
- The output is just the final output from an agent invocation, so it will not include all the intermediate steps or tool calls, this is ok.
</Note>

<input>
{inputs}
</input>

<output>
{outputs}
</output>

<reference_outputs>
{reference_outputs}
</reference_outputs>
"""


# For structured LLM output
class CorrectnessScore(BaseModel):
    reasoning: str = Field(..., description="A concise reasoning for the score")
    score: bool = Field(
        ..., description="True if the output is correct, False if incorrect."
    )


# Create a structured LLM
correctness_evaluator_llm = init_chat_model(model=DEFAULT_MODEL).with_structured_output(
    CorrectnessScore
)


# Define the evaluator function
def correctness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Evaluate the correctness of the output against the reference output."""

    formatted_prompt = CORRECTNESS_PROMPT.format(
        inputs=inputs, outputs=outputs, reference_outputs=reference_outputs
    )

    eval_result = correctness_evaluator_llm.invoke(formatted_prompt)

    # return a dictionary with the format the evaluator expects
    return {
        "key": "correctness",
        "score": eval_result.score,
        "comment": eval_result.reasoning,
    }
'''),
    md('''
**Shortcut with `openevals`:** The manual implementation above is useful for understanding what's happening under the hood. In practice, `openevals` wraps all of it — the structured output model, the LLM call, and the return format — into a single factory function:

```python
from openevals.llm import create_llm_as_judge

correctness_evaluator = create_llm_as_judge(
    model=DEFAULT_MODEL,
    prompt=CORRECTNESS_PROMPT,  # same prompt template as above
    feedback_key="correctness",
)
```

The returned `correctness_evaluator` is a drop-in replacement — pass it directly to `client.evaluate()` the same way.
'''),
    md('''
#### Target Function

A target function is used to specify how `inputs` from our dataset are processed to produce `outputs` that we want to evaluate.

Our agent needs one more thing than the question: the **verified customer**. In the app, sign-in provides it. Here, the target function looks the customer up by the email in the question and passes it as run context, so the agent is called exactly the way the app calls it.
'''),
    code("AGENT = agent\n" + TARGET_FUNCTION),
    md('''
Now, let's test the `correctness` evaluator on a single example from our dataset to see how everything works
'''),
    code('''
# get an example from our dataset
example = next(
    client.list_examples(dataset_id=dataset.id, metadata={"example_number": 1})
)
pprint(example.inputs)
'''),
    code('''
# run the example inputs through our target function
output = target_function(example.inputs)
pprint(output)
'''),
    code('''
# score the agent output against the reference output
correctness_score = correctness_evaluator(
    inputs=example.inputs, outputs=output, reference_outputs=example.outputs
)
pprint(correctness_score)
'''),
    md('''
### Evaluator #2: Total Tool Calls

An evaluator that doesn't rely on a ground truth reference, but is a good thing to track as it can help reveal agent patterns and highlight inefficiencies
'''),
    code('''
from langsmith.schemas import Run


def count_total_tool_calls_evaluator(run: Run) -> dict:
    """
    Count total tool calls across the entire run (main agent + subagents).

    Returns a single 'score' metric with the total count.
    Use for tracking efficiency: fewer calls = more efficient.
    """

    def traverse_runs(run_obj: Run) -> int:
        """Recursively count all tool-type runs in the tree."""
        count = 0

        # Count this run if it's a tool execution
        if run_obj.run_type == "tool":
            count = 1

        # Recursively count child runs
        if hasattr(run_obj, "child_runs") and run_obj.child_runs:
            for child in run_obj.child_runs:
                count += traverse_runs(child)

        return count

    total_tools = traverse_runs(run)

    return {"key": "total_tool_calls", "score": total_tools}
'''),
    md('''
### Evaluator #3: Order-Specialist Tool Calls

Total tool calls counts everything in the run, including the main agent's `task` calls that hand work to a specialist and the product-policy specialist's document searches. To see how hard the order specialist works on its own, count only the tool calls inside it:

```
deep_support_agent                     (main agent)
├── task  ──────────────────────────   counted in total only
│   └── order-specialist
│       ├── get_customer_orders  ───   counted in both
│       └── get_order_items      ───   counted in both
└── task  ──────────────────────────   counted in total only
    └── product-policy-specialist
        └── search_policy_docs   ───   counted in total only
```
'''),
    code('''
def order_specialist_tool_calls_evaluator(run: Run) -> dict:
    """Count tool calls made inside the order-specialist subagent."""

    def traverse_runs(run_obj: Run, inside: bool = False) -> int:
        """Count tool runs that have an ancestor named "order-specialist"."""
        inside = inside or run_obj.name == "order-specialist"
        count = 1 if inside and run_obj.run_type == "tool" else 0
        for child in getattr(run_obj, "child_runs", None) or []:
            count += traverse_runs(child, inside)
        return count

    return {"key": "order_specialist_tool_calls", "score": traverse_runs(run)}
'''),
    md('''
These evaluators don't depend on reference outputs to produce a score, but rather use metadata from the target function's execution on a given example. This is flexibly handled in the LangSmith SDK by passing a `Run` object as input to the evaluator.

> Note: see [this docs page](https://docs.langchain.com/langsmith/code-evaluator#evaluator-args) for a list of all arguments accepted by an evaluator function

Let's walk through an example to make this clear.
'''),
    code('''
# get a recent sample run from our project
runs = client.list_runs(
    project_name=os.environ.get("LANGSMITH_PROJECT", "langsmith-agent-lifecycle-workshop"),  # Your project
    filter="""and(eq(is_root, true), eq(name, "deep_support_agent"))""",  # get a deep agent run
    limit=1,
)
run = next(runs)

# Fetch the complete run with all children
full_run = client.read_run(run.id, load_child_runs=True)
'''),
    code('''
# we can inspect the full run metadata
# vars(full_run)

# or just look at the child runs
vars(full_run).get("child_runs")
'''),
    code('''
# now lets pass the run to our evaluators
print(count_total_tool_calls_evaluator(full_run))
print(order_specialist_tool_calls_evaluator(full_run))
'''),
    md('''
## 5. Run an experiment on the full dataset

Now we can use our target_function and three evaluators to programmatically run an offline evaluation over each example in our dataset - this is called an "experiment" in LangSmith.
'''),
    code('''
# Disable parallelism warnings from the tokenizers library to keep notebook output clean
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Run the experiment
results = client.evaluate(
    target_function,
    data=dataset_name,
    evaluators=[correctness_evaluator, count_total_tool_calls_evaluator, order_specialist_tool_calls_evaluator],
    experiment_prefix="deep-agent-baseline",
    description="Evaluate the final answer correctness and tool calls of the deep agent on the baseline dataset",
    max_concurrency=5,
)
'''),
    md('''
## 6. Error Analysis in LangSmith UI

Now let's analyze our baseline performance in the LangSmith UI via the link above. Sort by each column and open the traces behind the low scores:

| Look at | What to look for |
|---|---|
| `order_specialist_tool_calls` | Long chains of rigid lookups: `get_customer_orders` → `get_order_items` per order → `get_order_item_price` per item. Totals and counts get added up in the model's head. A score of exactly **15** means the specialist hit its tool-call limit and stopped before finishing |
| `correctness` on account questions | Questions about the customer's own record (phone, segment): no order tool reads the customer record |
| `correctness` on policy and product answers | Answers marked wrong for adding extra detail, or for masking data for privacy. That's the judge, not the agent: we come back to it when we align the judge |
| The cross-customer example | The answer refuses and shows nothing from the other customer's order |
'''),
]

# ============================================================================
# SECTION 2: Eval-driven development (mirrors module_2/section_2_eval_driven_development.ipynb)
# ============================================================================
s2 = [
    md('''
# Module 5, Section 2: Eval-Driven Development

The benefit of building out a dataset and eval metrics upfront is that we have a quantitative signal that we can use to understand how changes to our app impact downstream performance. Without this, we're just flying blind!


<div align="center">
    <img src="../../images/eval_process.png">
</div>

### Systematically Improving Our Application

Our baseline evaluation revealed weaknesses in the deep agent's order specialist:

**The Problem:**
- ❌ **Excessive tool calls**: Sequential chains of `get_customer_orders` → multiple `get_order_items` → multiple `get_order_item_price` calls, etc.
- ❌ **Missing capabilities**: Can't aggregate (SUM, COUNT, AVG), filter (WHERE), or JOIN across tables - so relies on in-memory math
- ❌ **Limited flexibility**: Rigid tools can't adapt to complex or novel queries, and none of them reads the customer's own record

**Possible Solution:**
Give the order specialist a flexible SQL tool that generates custom queries at runtime, scoped to the signed-in customer's data.

Let's use our evaluation setup to drive a targeted improvement!
'''),
    md('''
## 1. Setup

We'll give the order specialist a SQL tool that can answer complex questions about the customer's orders with a single query.

<div align="center">
    <img src="../../images/order_specialist_improvement.svg" width="700">
</div>
'''),
    code('''
import warnings
from dotenv import load_dotenv

# Load .env before any workshop import: config.py picks the models from it at import time
load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=r".*is deprecated and will be removed after", category=DeprecationWarning)

from tools.database import query_my_orders

# The tool's description carries the schema the model needs to write queries
print(query_my_orders.description)
'''),
    md('''
## 2. Build SQL Agent

In Module 2 the SQL agent got `execute_sql`, a tool that runs any SELECT. That can't work here: the order specialist serves a signed-in customer, and a raw SQL tool would let them read **every** customer's orders. The customer-scope guard only checks `customer_id` and `order_id` arguments, and a SQL string has neither.

So the tool enforces the scope itself, from the verified customer in run context:

```
SupportContext(customer_id="CUST-010")      set by the app, not the conversation
        │
        ▼
query_my_orders(sql)
   1. read-only connection to techhub.db
   2. temp views: orders, order_items, customers  ← only CUST-010's rows
   3. authorizer: reads of the views and the public products table only
   4. run the query (row cap, 2-second limit)
        │
        ▼
"SELECT ... FROM orders"  sees CUST-010's orders, and nobody else's
```
'''),
    md("The core of `query_my_orders` ([full source](../../tools/database.py)):\n\n```python\n" + QUERY_MY_ORDERS_EXCERPT + "\n```"),
    md('''
Now an agent that writes those queries, using the `create_agent()` abstraction with the same context schema and model as the deep agent's order specialist:
'''),
    code('''
from langchain.agents import create_agent
from agents.deep_support_agent import SupportContext
from config import DEEP_AGENT_SMALL_MODEL  # the model the deep agent's specialists run on

sql_agent = create_agent(
    model=DEEP_AGENT_SMALL_MODEL,
    tools=[query_my_orders],
    name="sql_agent",
    system_prompt="You are TechHub's order specialist. Answer with one SQL query when you can, and report exactly what it returns.",
    context_schema=SupportContext,
)
sql_agent
'''),
    md('''
#### 🔒 Production Security Note

In Module 2, the SQL tool blocked writes with keyword filtering. This tool also has to keep each customer inside their own data, so it uses several layers:

| Layer | What it blocks |
|---|---|
| Read-only connection (`mode=ro`) | Any write to the database |
| Temp views over the verified customer's rows | Reading another customer's orders, order items, or account |
| SQLite authorizer | Reading the underlying tables directly, `PRAGMA`, `ATTACH`, writes |
| Row cap and 2-second limit | Huge results and runaway queries |
| Customer ID from run context, validated | The conversation choosing whose data to read |

In production PostgreSQL, you'd add database-level controls too: a read-only role and row-level security keyed to the signed-in customer.
'''),
    md('''
## 3. Quick Demo

Let's test the SQL agent on a query that previously took a chain of lookups, as the customer who owns the order:
'''),
    code('''
# Test on a query that requires joining orders, items, and products
question = "What items were in order ORD-2023-0002? How much did each cost?"

result = sql_agent.invoke(
    {"messages": [{"role": "user", "content": question}]},
    context=SupportContext(customer_id="CUST-010"),
)

for message in result["messages"]:
    message.pretty_print()
'''),
    md('''
✅ **Success!** The SQL agent generates a custom query with JOINs to answer the question in a single tool call.

Now the same question from a **different** customer. The query runs, but only over that customer's rows, so the other customer's order isn't there:
'''),
    code('''
result = sql_agent.invoke(
    {"messages": [{"role": "user", "content": question}]},
    context=SupportContext(customer_id="CUST-003"),
)

result["messages"][-1].pretty_print()
'''),
    md('''
Check the LangSmith traces to see the generated SQL queries!
'''),
    md('''
## 4. Integrate SQL Agent with the Deep Agent

Now let's swap the order specialist's rigid tools for this SQL tool in the full deep agent. `order_tools="sql"` gives the order specialist `query_my_orders` instead of the five lookups:

<div align="center">
    <img src="../../images/order_specialist_improvement.svg" width="500">
</div>
'''),
    code('''
from agents.deep_support_agent import create_deep_support_agent

# Compose the deep agent with the SQL order specialist instead of the rigid one
improved_agent = create_deep_support_agent(order_tools="sql")
'''),
    md('''
Quick test:
'''),
    code('''
import uuid

# New thread
thread_id = uuid.uuid4()
config = {"configurable": {"thread_id": thread_id}}

# The app has signed the customer in, so their ID comes from run context
result = improved_agent.invoke(
    {"messages": [{"role": "user", "content": "Whats the status of my recent order?"}]},
    config=config,
    context=SupportContext(customer_id="CUST-003"),
)
'''),
    code('''
for message in result["messages"]:
    message.pretty_print()
'''),
    md('''
## 5. Re-evaluate Performance

Now let's run the same evaluation on the same dataset to quantitatively see how it impacts our performance metrics.
'''),
    code('''
# Import evaluators from Section 1 (now packaged in evaluators module)
from evaluators import (
    correctness_evaluator,
    count_total_tool_calls_evaluator,
    order_specialist_tool_calls_evaluator,
)
'''),
    code("from langsmith import Client\n\nclient = Client()\n\nAGENT = improved_agent\n" + TARGET_FUNCTION + '''

# The Section 1 dataset: the most recent one with its name prefix
dataset = max(
    client.list_datasets(dataset_name_contains="techhub-deep-agent-baseline-"),
    key=lambda ds: ds.created_at,
)

# Run evaluation on same dataset
results = client.evaluate(
    target_function,
    data=dataset.name,  # Same dataset as section 1
    evaluators=[correctness_evaluator, count_total_tool_calls_evaluator, order_specialist_tool_calls_evaluator],
    experiment_prefix="deep-agent-sql",
    description="Evaluate the SQL order specialist's flexible queries vs baseline rigid tools",
    max_concurrency=5,
)
'''),
    md('''
## 6. Compare Results in LangSmith

Now let's analyze our improvement using LangSmith's comparison features. Open both experiments side by side:
'''),
    code('''
experiments = sorted(client.list_projects(reference_dataset_id=dataset.id), key=lambda p: p.start_time)
baseline = next(p for p in reversed(experiments) if p.name.startswith("deep-agent-baseline"))
improved = next(p for p in reversed(experiments) if p.name.startswith("deep-agent-sql"))

print("Baseline:", baseline.name)
print("Improved:", improved.name)
print(f"📊 Compare: {dataset.url}/compare?selectedSessions={baseline.id},{improved.id}")
'''),
    md('''
What to expect:

| Metric | Direction | Why |
|---|---|---|
| `order_specialist_tool_calls` | ⬇️ Down sharply | One query replaces a chain of lookups |
| `total_tool_calls` | ⬇️ Down | Same reason; delegations and doc searches stay about the same |
| `correctness` | ⬆️ Same or better | Aggregations are computed by SQL instead of in the model's head, and the customer record is now readable |
| Cross-customer example | Still refused | The SQL only ever sees the signed-in customer's rows |

Totals can hide regressions, so also check any example that flipped from correct to wrong and open its trace: a change can fix many questions and break one.

Some answers will still be marked wrong for adding detail or masking data for privacy. That's the judge, not the agent: aligning the judge is next.
'''),
]

# ============================================================================
# SECTION 3: Aligning the judge (mirrors module_2/bonus_align_llm_judge.ipynb;
# see docs/2026-11-12-module-5-section-3-prd.md)
# ============================================================================
s3 = [
    md('''
# Module 5, Section 3: Aligning an LLM-as-Judge

In Sections 1 and 2, every decision about the deep agent rested on one number: the `correctness` score from our LLM-as-judge. We used it to set a baseline and to justify replacing the order specialist's rigid tools with SQL. We never checked whether the judge agrees with a person.

A judge is **aligned** when it reaches the same verdict a human would on the same output. In this notebook we measure that agreement against human labels, find where the judge is wrong, and fix its rubric until the two agree.

| Step | What we do |
|---|---|
| 1. Golden set | Load 33 frozen deep-agent outputs, each labeled correct or incorrect by a person |
| 2. Measure | Run the Sections 1–2 judge over them and count agreements with the labels |
| 3. Diagnose | Read the disagreements and group them by cause |
| 4. Fix | Add one rubric rule per cause and re-measure |
'''),
    md('''
<div align="center">
    <img src="../../images/align-evals-workflow.png" width="900">
</div>
'''),
    md("## Setup"),
    code('''
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

# Make the repo root importable regardless of the kernel's working directory.
REPO_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config.py").exists())
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")
warnings.filterwarnings("ignore", category=UserWarning)

from langchain.chat_models import init_chat_model
from langsmith import Client
from pydantic import BaseModel, Field

from evaluators.evaluators import CORRECTNESS_PROMPT

client = Client()
'''),
    md('''
We pin the judge model instead of reading it from `WORKSHOP_MODEL`. A judge is a measuring instrument: if its model changes, every score it produced before means something different.
'''),
    code('''
JUDGE_MODEL = "openai:gpt-5-mini"
'''),
    md('''
## 1. Load the golden set

`golden_set.json` holds 33 items. Each one has a customer question, the reference answer from Section 1's dataset, a deep-agent output, and a human label:

- **26 outputs are unedited.** They are the final answers from the Section 1 experiment (rigid order tools) and the Section 2 experiment (scoped SQL), one per question for each.
- **7 outputs are edited copies** of those answers. Each edit introduces one specific mistake, such as claiming a refund was issued, or fixes one, such as giving the full phone number instead of a masked one, so that both labels appear for each kind of mistake.

The outputs are frozen, so the only thing that changes between runs in this notebook is the judge.
'''),
    code('''
GOLDEN_SET_PATH = REPO_ROOT / "workshop_modules" / "module_5" / "golden_set.json"
golden_set = json.loads(GOLDEN_SET_PATH.read_text())
GOLD = {item["id"]: item for item in golden_set}

labels = Counter(item["human_label"] for item in golden_set)
print(f"{len(golden_set)} items: {labels[True]} labeled correct, {labels[False]} labeled incorrect\\n")
print(Counter(item["bucket"] for item in golden_set))
'''),
    md('''
Every item has a `bucket` (the kind of output it is) and a `label_note` (why the labeler chose that label):

| Bucket | Label | What the output does |
|---|---|---|
| `ok` | correct | Answers the question accurately |
| `refused` | correct | Declines to share another customer's order |
| `cut_off` | incorrect | Stops short because the order specialist hit its tool-call limit: a SKU instead of a name, a total marked "at least", wrong counts |
| `partial` | incorrect | Answers one half of a two-part question, or gives only one of two return windows |
| `masked` | incorrect | Masks the phone number the verified customer asked for |
| `fabricated` | incorrect | Right facts, plus an action the agent didn't or can't take ("I've issued a refund") |
| `numbers` | incorrect | A breakdown that doesn't add up to the total it supports |
| `wrong` / `no_answer` | incorrect | Wrong answer, or no answer |

Two principles decided the close calls:

- **A right headline with wrong supporting facts is incorrect.** Customers act on the details.
- **Judge against what the customer asked, not everything in the reference.** Extras in the reference aren't required, and details count when the question is about them.

> **Note:** The judge gets aligned to these labels, so they deserve the most scrutiny in this notebook. Read a few `label_note` values before trusting any agreement number below.
'''),
    code('''
for item_id in ["sql-1", "sql-6", "edit-sql-7-refund-offer"]:
    item = GOLD[item_id]
    print(f"--- {item_id} [{item['bucket']}] human_label={item['human_label']}")
    print(f"Q:     {item['question']}")
    print(f"Note:  {item['label_note']}\\n")
'''),
    md('''
#### 🔒 Production Security Note

The emails and phone numbers in this dataset belong to synthetic TechHub customers. With real traffic, a golden set is a copy of customer data that more people see and that lives longer than the original trace:

1. **Scrub before labeling**: replace emails, names and phone numbers with tokens before outputs reach an annotation queue or a dataset
2. **Scrub before judging**: the judge model sees everything you pass to it, so send it the fields it needs and nothing else
3. **Match access controls**: give the dataset the same access and retention rules as the project the traces came from

The deep agent's own PII redaction doesn't make a golden set safe: it redacts what the model sees, not what you copy out of traces and outputs.
'''),
    md('''
### 1.1 Create the dataset in LangSmith

Each example stores the question as input and the reference answer as output. The `example_id` in the inputs lets the target function find the frozen output. The judge never sees it, and never sees the human label.

Re-running this cell reuses the dataset and only adds missing examples. It never deletes, so labels and experiments attached to existing examples stay intact.
'''),
    code('''
DATASET_NAME = "techhub-deep-agent-judge-alignment"

if client.has_dataset(dataset_name=DATASET_NAME):
    dataset = client.read_dataset(dataset_name=DATASET_NAME)
    print(f"Reusing dataset: {dataset.name}")
else:
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Frozen TechHub deep-agent outputs with human correctness labels, for aligning the correctness judge.",
    )
    print(f"Created dataset: {dataset.name}")

existing_ids = {ex.inputs.get("example_id") for ex in client.list_examples(dataset_id=dataset.id)}
missing = [item for item in golden_set if item["id"] not in existing_ids]
if missing:
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[
            {"example_id": item["id"], "messages": [{"role": "user", "content": item["question"]}]}
            for item in missing
        ],
        outputs=[{"messages": [{"role": "assistant", "content": item["reference"]}]} for item in missing],
        metadata=[{"bucket": item["bucket"]} for item in missing],
    )
print(f"Added {len(missing)} example(s). Dataset: {dataset.url}")
'''),
    md('''
### 1.2 Target function

The target function returns the frozen output for each example instead of calling the agent. Every experiment in this notebook therefore grades the exact same 33 outputs.
'''),
    code('''
def frozen_agent(inputs: dict) -> dict:
    """Return the stored agent output for this example."""
    output = GOLD[inputs["example_id"]]["output"]
    return {"messages": [{"role": "assistant", "content": output}]}
'''),
    md('''
## 2. Measure the Sections 1–2 judge

`make_judge` turns a prompt into an evaluator with the same structure as `correctness_evaluator` in `evaluators/evaluators.py`. It returns two scores per example:

- **`correctness`**: the judge's verdict
- **`matches_human`**: 1 if that verdict equals the human label, 0 if not

**Agreement** is the share of examples where `matches_human` is 1.
'''),
    code('''
class CorrectnessScore(BaseModel):
    """Structured output schema for correctness evaluation."""

    reasoning: str = Field(..., description="A concise reasoning for the score")
    score: bool = Field(..., description="True if the output is correct, False if incorrect.")


judge_llm = init_chat_model(JUDGE_MODEL).with_structured_output(CorrectnessScore)


def make_judge(prompt: str):
    def judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
        # Only the conversation reaches the judge: no example_id, no human label.
        result = judge_llm.invoke(
            prompt.format(
                inputs={"messages": inputs["messages"]},
                outputs=outputs,
                reference_outputs=reference_outputs,
            )
        )
        human_label = GOLD[inputs["example_id"]]["human_label"]
        return {
            "results": [
                {"key": "correctness", "score": result.score, "comment": result.reasoning},
                {"key": "matches_human", "score": int(result.score == human_label), "comment": f"human_label={human_label}"},
            ]
        }

    return judge
'''),
    md('''
We also set aside a **hold-out**: six labeled items, chosen before measuring anything, that the rubric rules are never written against. If a rule only works on the items it was written for, the hold-out shows it.

`report` reads an experiment's results back and prints the agreement (overall, on the items the rules are written against, and on the hold-out), a confusion matrix of human label against judge verdict, and every disagreement with the judge's reasoning.
'''),
    code('''
HOLDOUT = {"sql-4", "rigid-13", "rigid-3", "sql-9", "sql-10", "edit-sql-2-account-updated"}


def report(results) -> float:
    rows = []
    for row in results:
        example_id = row["example"].inputs["example_id"]
        scores = {r.key: r for r in row["evaluation_results"]["results"]}
        rows.append((GOLD[example_id], bool(scores["correctness"].score), scores["correctness"].comment))

    def agreement_on(selected):
        return sum(item["human_label"] == verdict for item, verdict, _ in selected) / len(selected)

    agreement = agreement_on(rows)
    rule_items = [r for r in rows if r[0]["id"] not in HOLDOUT]
    holdout = [r for r in rows if r[0]["id"] in HOLDOUT]
    matrix = Counter((item["human_label"], verdict) for item, verdict, _ in rows)

    print(f"Agreement: {agreement:.0%} ({round(agreement * len(rows))}/{len(rows)})")
    print(f"  rule items: {agreement_on(rule_items):.0%}   hold-out: {agreement_on(holdout):.0%}\\n")
    print("                    judge=correct  judge=incorrect")
    print(f"human=correct       {matrix[(True, True)]:>13}  {matrix[(True, False)]:>15}")
    print(f"human=incorrect     {matrix[(False, True)]:>13}  {matrix[(False, False)]:>15}\\n")
    for item, verdict, reasoning in rows:
        if item["human_label"] != verdict:
            holdout_tag = " (hold-out)" if item["id"] in HOLDOUT else ""
            print(f"✗ {item['id']} [{item['bucket']}]{holdout_tag} human={item['human_label']} judge={verdict}")
            print(f"    judge: {reasoning[:220]}")
    return agreement


agreement_by_version = {}
'''),
    md('''
Now run the judge from Sections 1 and 2, unchanged, over the golden set.
'''),
    code('''
results_v0 = client.evaluate(
    frozen_agent,
    data=DATASET_NAME,
    evaluators=[make_judge(CORRECTNESS_PROMPT)],
    experiment_prefix="deep-judge-v0-sections-1-2",
    max_concurrency=8,
)
agreement_by_version["v0 (Sections 1–2)"] = report(results_v0)
'''),
    md('''
### 2.1 Analyze Results

Read the disagreements before changing anything. Look at the `bucket` of each one and at the judge's reasoning, and group them by cause.

**Common failure patterns to look for:**
- **The judge passes outputs the human failed.** The judge is too lenient on something the labeler cares about.
- **The judge fails outputs the human passed.** The rubric asks for something the labeler doesn't.
- **Disagreements cluster in one or two buckets.** Each cluster usually traces back to one sentence in the rubric that is missing or too loose.

On our runs, the judge agreed with the labels on almost everything, including the close calls, and the disagreements were in one bucket:

| Bucket | Why the judge passed it |
|---|---|
| `fabricated` | The rubric's `<Note>` says "It's ok if the output provides additional information". The judge reads an invented action ("I've also issued a refund", "I've updated your phone number") as an acceptable extra. |

Occasionally it also passed a `masked` answer ("withholding the full number for privacy does not make the response incorrect").
'''),
    md('''
## 3. Fix the rubric, one cause at a time

Each fix below adds rules for exactly one cause and re-runs the judge on the same 33 outputs. Changing one thing per run tells you which rule moved the number.

### 3.1 Fix 1: invented actions and claims

The deep agent can look up orders, products, account details and policies, and it can **request** a refund, which waits for a person to approve it. The rubric now says so: offering a refund request is fine, but claiming a refund was issued, or any action it can't take, is not.

We only add the rule. In our runs, also loosening the `<Note>` about additional information made the judge more lenient on other buckets.
'''),
    code('''
RULE_NO_INVENTED_ACTIONS = (
    "  - Does not offer or claim actions the assistant can't take. The assistant can look up orders, products, account "
    "details, and store policies, and can submit a refund request, which a person must approve before anything is refunded. "
    "Claiming that a refund was issued or approved, or offering or claiming to update account data, place or cancel orders, "
    "open returns, send messages, labels, or codes, apply discounts or credits, or contact other teams or systems makes the "
    "output incorrect, even if everything else is right. Offering to look something up, reformat the answer, or submit a "
    "refund request is fine.\\n"
    "  - Does not claim the customer asked for something they didn't. Details the assistant looked up, such as the "
    "customer's name or ID, are fine.\\n"
)

PROMPT_V1 = CORRECTNESS_PROMPT.replace(
    "  - Is logically consistent\\n",
    "  - Is logically consistent\\n" + RULE_NO_INVENTED_ACTIONS,
)
assert PROMPT_V1 != CORRECTNESS_PROMPT, "the replace() target didn't match"

results_v1 = client.evaluate(
    frozen_agent,
    data=DATASET_NAME,
    evaluators=[make_judge(PROMPT_V1)],
    experiment_prefix="deep-judge-v1-no-invented-actions",
    max_concurrency=8,
)
agreement_by_version["v1 (+ no invented actions)"] = report(results_v1)
'''),
    md('''
Compare the disagreements with the previous run, not just the totals. A new rule can fix one bucket and loosen another.

On our runs, Fix 1 fixed both invented-action outputs, including the hold-out one the rule was never written against. But with the action rule in place, the judge sometimes passes answers that leave part of the question unanswered, as long as they claim nothing they can't do ("it does not claim any prohibited actions, so it meets the rubric"): a masked phone number, a SKU instead of the item name, or "I couldn't verify stock" when the product is in stock. Which of these slip through varies from run to run.
'''),
    md('''
### 3.2 Fix 2: answer what was asked

The customer is already verified, so masking their own phone number doesn't answer their question. And "I couldn't verify" isn't an answer when the information exists. The new rule requires the information itself.

The rule is scoped to what the customer **asks for**. Worded more broadly ("give the customer's account details in full"), it made the judge fail good answers for not repeating the customer's details.
'''),
    code('''
RULE_ANSWER_WHAT_WAS_ASKED = (
    "  - Answers what the customer asked with the information itself. If the customer asks for their own account "
    "details (for example, their phone number or account type), the output must give them in full: the customer is "
    "already verified, so masking or withholding them doesn't answer the question. If the output says it couldn't "
    "find, check, or verify something the question asks for, and the reference output contains that information, that "
    "part is unanswered and the output is incorrect.\\n"
)

PROMPT_V2 = PROMPT_V1.replace(
    "  - Addresses all parts of the question\\n",
    "  - Addresses all parts of the question\\n" + RULE_ANSWER_WHAT_WAS_ASKED,
)
assert PROMPT_V2 != PROMPT_V1, "the replace() target didn't match"

results_v2 = client.evaluate(
    frozen_agent,
    data=DATASET_NAME,
    evaluators=[make_judge(PROMPT_V2)],
    experiment_prefix="deep-judge-v2-answer-what-was-asked",
    max_concurrency=8,
)
agreement_by_version["v2 (+ answer what was asked)"] = report(results_v2)
'''),
    md("### 3.3 Compare the versions"),
    code('''
for version, agreement in agreement_by_version.items():
    print(f"{version:<32} {agreement:>4.0%}  {'█' * round(agreement * 30)}")
'''),
    md('''
Open the three experiments side by side in LangSmith (select them on the dataset's **Experiments** tab and click **"Compare"**) and filter on `matches_human = 0` to see which examples changed between versions.

Before trusting the final number, check three things:

- **Read the remaining disagreements.** For each one, decide whether the judge is wrong or the label is. On our runs, the one left was `edit-sql-1-breakdown-fixed`: the judge says the Logitech MX Master 3S mice shouldn't count as keyboards. The catalog files them under Keyboards and the reference total counts them, so the label follows the data. But the judge has found a real data-quality problem: the fix is in the catalog, not the rubric. If you agree with the judge on an item, change the label, not the rubric.
- **Check the hold-out.** The rules were written against the other 27 items. If agreement on the hold-out drops while the rest rises, a rule is fitted to its examples. On our runs, the hold-out went from 78–83% to 100%, but six items are few.
- **Add labels before calling the judge done.** 33 examples are enough to find failure modes, not to certify a judge. Re-measure on new labeled outputs that weren't used to write the rules.

> **Note:** The judge model is not deterministic. Re-running a version can move agreement by an item or two. Compare versions on repeated runs, not on a single one. In a single run, v1 and v2 can tie; over three runs each, v1 averaged 90% and v2 97%.
'''),
    md('''
## 4. Optional: label the outputs yourself

The labels above come from one reviewer. To align the judge to *your* standard, label the outputs in an annotation queue and compare your labels with `golden_set.json`. Where you disagree, edit the file: the agreement numbers above are only as good as these labels.

Set `LABEL_IN_QUEUE = True` to create a queue that contains the runs from the v0 experiment.
'''),
    code('''
LABEL_IN_QUEUE = False

if LABEL_IN_QUEUE:
    QUEUE_NAME = "techhub-deep-agent-judge-alignment-labels"
    existing = list(client.list_annotation_queues(name=QUEUE_NAME))
    queue = existing[0] if existing else client.create_annotation_queue(
        name=QUEUE_NAME,
        description="Label each TechHub deep-agent output correct or incorrect against the reference answer.",
    )
    run_ids = [row["run"].id for row in results_v0]
    client.add_runs_to_annotation_queue(queue.id, run_ids=run_ids)
    print(f"Added {len(run_ids)} runs to queue '{queue.name}'. Open Annotation Queues in LangSmith to label them.")
'''),
    md('''
## 5. Use the aligned judge

`PROMPT_V2` is saved in `evaluators/evaluators.py` as `DEEP_AGENT_CORRECTNESS_PROMPT`, with `deep_agent_correctness_evaluator`, a drop-in replacement for `correctness_evaluator` on the same pinned model. The next section compares Jev against it. The cell below checks that the saved judge is the one you just measured.

Keep the golden set next to the judge. When you change the rubric or the judge model, re-run this notebook first: if agreement drops, the change made the judge worse, whatever it does to the agent's scores.

LangSmith also runs this loop in the UI with the **Align Evaluator**: you label runs in a queue, then test the judge prompt against your labels in the Evaluator Playground. See [Improve LLM-as-judge evaluators using human feedback](https://docs.langchain.com/langsmith/improve-judge-evaluator-feedback) and the [video walkthrough](https://www.youtube.com/watch?v=-9o94oj4x0A).

| Step in this notebook | Same step in the UI |
|---|---|
| 1. Golden set + labels | <img src="https://mintcdn.com/langchain-5e9cc07a/E8FdemkcQxROovD9/langsmith/images/add-to-evaluator-queue.gif?s=3c457faaaf2c7f31425ba510a518260e" width="420"> |
| 2. Measure agreement | <img src="https://mintcdn.com/langchain-5e9cc07a/0B2PFrFBMRWNccee/langsmith/images/evaluator-pg.gif?s=c8108ce3abc95ce756fcbd1b3726916d" width="420"> |
| 2.1 Read the judge's reasoning | <img src="https://mintcdn.com/langchain-5e9cc07a/0B2PFrFBMRWNccee/langsmith/images/enable-reasoning.gif?s=d6ed09e4149a63723ef9305544b8b652" width="420"> |
'''),
    code('''
from evaluators.evaluators import DEEP_AGENT_CORRECTNESS_PROMPT, DEEP_AGENT_JUDGE_MODEL

assert PROMPT_V2 == DEEP_AGENT_CORRECTNESS_PROMPT and JUDGE_MODEL == DEEP_AGENT_JUDGE_MODEL, "evaluators/ is out of sync with this notebook"
print(PROMPT_V2)
'''),
]

# ============================================================================
# SECTION 4: Jev as a judge (see docs/2026-11-12-module-5-section-4-prd.md)
# ============================================================================
s4 = [
    md('''
# Module 5, Section 4: Jev as a Judge

Section 3 ended with an aligned LLM judge: 97% agreement with human labels, about 4 seconds and a few hundred output tokens per answer. Grading every production trace that way adds up. **Jev**, TypeSafe's decision model, answers typed questions with probabilities instead of writing text, in a fraction of a second. Can it do the judge's job, and how would you know?

```
LLM judge                                   Decision model (Jev)
─────────                                   ────────────────────
prompt: rubric + question + answer          state: question + reference + answer
        │                                          (no grading instructions)
        ▼                                   questions: typed, each with what yes and no mean
reasoning text  ──►  verdict: True/False           │
                                                   ▼
                                            probability per question  ──►  threshold  ──►  verdict
```

We grade the **same 33 human-labeled answers** as Section 3, so the numbers compare directly:

| Step | What we do |
|---|---|
| 1. Jev in one cell | A quick recap of Jev's question types |
| 2. Jev as an evaluator | A judge becomes a state, questions, and a threshold |
| 3. Measure | One question, against the human labels |
| 4. Fix | The aligned rubric as questions, one cause at a time |
| 5. Pick the threshold | Choose it on the rule items, check the hold-out, and cascade the uncertain middle |
| 6. Compare the judges | Agreement, speed, and cost side by side |
| 7. In the UI | The same evaluator as a Decision Model Evaluator |
'''),
    md('''
## Setup

Jev runs through the LangSmith LLM Gateway with a key from a workspace that has Jev. `utils/jev.py` picks the key (first match wins, used only for Jev):

| Where you are | What to set |
|---|---|
| **A workshop** | `JEV_API_KEY` in `.env`: the workshop key you were given |
| **A LangChain-managed Mac** | Nothing, if `LC_GATEWAY_KEY` is in your environment. If you started Jupyter from a terminal, add `GATEWAY_ENV_FILE=/etc/lc_internal/gateway_env` to `.env` |
| **Your own workspace** | Add a `TYPESAFE_API_KEY` provider secret to the workspace your key belongs to |

Without a working key, every Jev cell skips itself and shows the results from our runs instead. `uv run python verify_setup.py` reports which key Jev is using.
'''),
    code('''
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

# Make the repo root importable regardless of the kernel's working directory.
REPO_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config.py").exists())
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")
warnings.filterwarnings("ignore", category=UserWarning)

from langchain_core._api import LangChainBetaWarning
from langchain_typesafe import Choice, Noul, NoulCriteria

warnings.filterwarnings("ignore", category=LangChainBetaWarning)  # TypeSafeClassifier is in beta
from langsmith import Client

from evaluators.evaluators import jev_state
from utils.jev import JEV_MODEL, jev_classifier, jev_key_source

client = Client()

source = jev_key_source()
try:
    jev_classifier().invoke({"state": "Hello!", "questions": {"q": Noul(instructions="Is this a greeting?")}})
    JEV_AVAILABLE = True
    print(f"✓ Jev {JEV_MODEL}, key from {source[0]}")
except Exception as e:  # e.g. 424: the key's workspace has no TYPESAFE_API_KEY provider secret
    JEV_AVAILABLE = False
    print(f"⏭️  Jev unavailable (key from {source[0] if source else 'nowhere'}: {type(e).__name__}). The Jev cells below show our results instead.")
'''),
    md('''
## 1. Jev in one cell

Module 4 Section 3 introduced Jev's three question types: a **`Noul`** returns the probability that a statement is true, a **`Choice`** picks one option with a probability for each, and a **`Score`** places the state on an ordered scale. Every answer is a number you can threshold, not text you have to parse.
'''),
    code('''
if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. On our run: damaged 0.99, intent 'refund' (confidence 1.0).")
else:
    response = jev_classifier().invoke({
        "state": "Customer: my monitor arrived with a cracked screen and I want my money back.",
        "questions": {
            "damaged": Noul(instructions="Does the customer report a damaged item?"),
            "intent": Choice(instructions="What does the customer want?", criteria={"refund": None, "replacement": None, "information": None}),
        },
    })
    print("damaged:", response.nouls["damaged"].noul)
    print("intent: ", response.choices["intent"].choice, f"(confidence {response.choices['intent'].confidence:.2f})")
'''),
    md('''
## 2. Jev as an evaluator

An LLM judge reads a prompt that mixes instructions and data. A decision model separates them:

```
state      Customer question:                 ← what to judge, and nothing else
           What's the most expensive item I've ever purchased? ...

           Reference answer (ground truth):
           Your most expensive item was the Dell XPS 13 ... at $1,399.00.

           Agent answer:
           Your most expensive single item was the Dell XPS 13 ...

questions  correct: Noul(instructions=..., criteria=NoulCriteria(true=..., false=...))
                                              ← the grading criteria live here
threshold  correct if probability ≥ 0.5       ← turns a probability into a verdict
```

Question wording matters more than the threshold: say exactly what yes and no mean, including what should *not* count.

We grade the same golden set and dataset as Section 3. The cell below reuses the dataset if Section 3 created it.
'''),
    code('''
GOLDEN_SET_PATH = REPO_ROOT / "workshop_modules" / "module_5" / "golden_set.json"
golden_set = json.loads(GOLDEN_SET_PATH.read_text())
GOLD = {item["id"]: item for item in golden_set}
HOLDOUT = {"sql-4", "rigid-13", "rigid-3", "sql-9", "sql-10", "edit-sql-2-account-updated"}  # same as Section 3
DATASET_NAME = "techhub-deep-agent-judge-alignment"

if client.has_dataset(dataset_name=DATASET_NAME):
    dataset = client.read_dataset(dataset_name=DATASET_NAME)
else:
    dataset = client.create_dataset(dataset_name=DATASET_NAME, description="Frozen TechHub deep-agent outputs with human correctness labels.")
existing_ids = {ex.inputs.get("example_id") for ex in client.list_examples(dataset_id=dataset.id)}
missing = [item for item in golden_set if item["id"] not in existing_ids]
if missing:
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"example_id": i["id"], "messages": [{"role": "user", "content": i["question"]}]} for i in missing],
        outputs=[{"messages": [{"role": "assistant", "content": i["reference"]}]} for i in missing],
        metadata=[{"bucket": i["bucket"]} for i in missing],
    )
print(f"{len(golden_set)} labeled answers. Dataset: {dataset.url}")


def frozen_agent(inputs: dict) -> dict:
    """Return the stored agent output for this example."""
    return {"messages": [{"role": "assistant", "content": GOLD[inputs["example_id"]]["output"]}]}
'''),
    md('''
`make_jev_judge` turns a set of questions and a threshold into an evaluator. Each question becomes its own feedback score; `correctness` is 1 when **every** question clears the threshold; `matches_human` compares that verdict with the label, as in Section 3.
'''),
    code('''
def make_jev_judge(questions: dict, threshold: float):
    def judge(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
        # Only the conversation reaches Jev: no example_id, no human label.
        state = jev_state(
            inputs["messages"][-1]["content"],
            reference_outputs["messages"][-1]["content"],
            outputs["messages"][-1]["content"],
        )
        response = jev_classifier().invoke({"state": state, "questions": questions})
        probabilities = {name: response.nouls[name].noul for name in questions}
        verdict = min(probabilities.values()) >= threshold
        human_label = GOLD[inputs["example_id"]]["human_label"]
        return {
            "results": [
                *({"key": name, "score": p} for name, p in probabilities.items()),
                {"key": "correctness", "score": int(verdict), "comment": f"lowest probability {min(probabilities.values()):.2f}"},
                {"key": "matches_human", "score": int(verdict == human_label), "comment": f"human_label={human_label}"},
            ]
        }

    return judge


def lowest_probabilities(results, questions) -> dict:
    """Each example's lowest question probability, read back from an experiment."""
    lowest = {}
    for row in results:
        scores = {r.key: r.score for r in row["evaluation_results"]["results"]}
        lowest[row["example"].inputs["example_id"]] = min(scores[name] for name in questions)
    return lowest


def report(lowest: dict, threshold: float) -> float:
    """Agreement with the labels at a threshold: all, rule items, hold-out, and every disagreement."""
    def agreement_on(ids):
        return sum((lowest[i] >= threshold) == GOLD[i]["human_label"] for i in ids) / len(ids)

    rule_items = [i for i in lowest if i not in HOLDOUT]
    agreement = agreement_on(list(lowest))
    print(f"\\nThreshold {threshold:.2f}. Agreement: {agreement:.0%}  (rule items {agreement_on(rule_items):.0%}, hold-out {agreement_on(HOLDOUT):.0%})")
    for i, p in sorted(lowest.items(), key=lambda kv: kv[1]):
        if (p >= threshold) != GOLD[i]["human_label"]:
            print(f"  ✗ {i} [{GOLD[i]['bucket']}]{' (hold-out)' if i in HOLDOUT else ''} human={GOLD[i]['human_label']} lowest probability={p:.2f}")
    return agreement


agreement_by_version = {}
'''),
    md('''
## 3. Measure: one question

Start with the simplest judge: a single question about correctness.
'''),
    code('''
SINGLE_QUESTION = {
    "correct": Noul(
        instructions="Is the agent answer correct for the customer's question, judged against the reference answer?",
        criteria=NoulCriteria(
            true="It gives the information the customer asked for, and its facts agree with the reference answer.",
            false="It gets a fact the customer asked about wrong, leaves part of the question unanswered, or claims something it can't back up.",
        ),
    ),
}

if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. On our runs at 0.50: 85-88% (hold-out 67%).")
else:
    results_single = client.evaluate(
        frozen_agent, data=DATASET_NAME, evaluators=[make_jev_judge(SINGLE_QUESTION, 0.5)],
        experiment_prefix="jev-judge-single-question", max_concurrency=8,
    )
    agreement_by_version["Jev, one question"] = report(lowest_probabilities(results_single, SINGLE_QUESTION), 0.5)
'''),
    md('''
### 3.1 Analyze Results

On our runs, one question fails in both directions: it fails good answers that add policy detail or skip prices the customer didn't ask for, and it passes a masked phone number and an invented account update. A single "is it correct?" question has no way to say *which* criterion matters.
'''),
    md('''
## 4. Fix: the aligned rubric as questions

Section 3's aligned rubric has three ideas: the facts agree with the reference (and with each other), the answer gives what was asked, and the agent claims only actions it can take. Ask Jev each one as its own question; an answer is correct only if all three pass.
'''),
    code('''
FACTS_AGREE = Noul(
    instructions="Do the facts in the agent answer agree with the reference answer, and with each other? Check totals, counts, prices, dates, items, and any breakdown against its own total.",
    criteria=NoulCriteria(
        true="Every fact the reference answer covers matches, and any breakdown adds up to the total it supports. Extra details the reference doesn't mention are fine.",
        false="A number, item, or fact contradicts the reference answer, or a breakdown doesn't add up to the total it supports.",
    ),
)
ANSWERS_INSTRUCTIONS = "Does the agent answer give the customer the information they asked for, for every part of the question?"
ANSWERS_TRUE = "It states the requested information itself for every part of the question."
ANSWERS_FALSE = "It leaves part unanswered: it masks or withholds the customer's own details, says it couldn't find, check, or verify something, or answers only part of the question."
POSSIBLE_ACTIONS = Noul(
    instructions="Does the agent answer stay within what the assistant can do: look things up, and submit refund requests that a person approves?",
    criteria=NoulCriteria(
        true="It only reports what it looked up, offers to look something else up or reformat, or offers to submit a refund request for a person to approve.",
        false="It claims or offers something else: says a refund was issued, updated account data, opened a return, sent an email or label, placed or cancelled an order, or contacted another team.",
    ),
)
RUBRIC_V1 = {
    "facts_agree": FACTS_AGREE,
    "answers_question": Noul(instructions=ANSWERS_INSTRUCTIONS, criteria=NoulCriteria(true=ANSWERS_TRUE, false=ANSWERS_FALSE)),
    "possible_actions": POSSIBLE_ACTIONS,
}

if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. On our runs at 0.50: 85%; both correct refusals fail answers_question (0.01-0.02).")
else:
    results_v1 = client.evaluate(
        frozen_agent, data=DATASET_NAME, evaluators=[make_jev_judge(RUBRIC_V1, 0.5)],
        experiment_prefix="jev-judge-rubric-v1", max_concurrency=8,
    )
    agreement_by_version["Jev, rubric questions"] = report(lowest_probabilities(results_v1, RUBRIC_V1), 0.5)
'''),
    md('''
Open the experiment and look at the per-question feedback columns: they say *which* question failed each answer. On our runs, the clearest cause was the two correct refusals (another customer's order): they fail `answers_question` at 0.01–0.02, because the false meaning counts any withheld information as a failure.

### 4.1 Fix: a correct refusal answers the question

One sentence in the false meaning, the same kind of fix as Section 3's rules. Watch the refusals' probabilities, not just the total: at a threshold of 0.50 the fix can look like it did nothing.
'''),
    code('''
REFUSAL_IS_AN_ANSWER = (
    " Declining because the order or data belongs to a different customer is not leaving it unanswered: "
    "when the reference answer also declines, that is the right answer."
)
RUBRIC_V2 = {
    **RUBRIC_V1,
    "answers_question": Noul(instructions=ANSWERS_INSTRUCTIONS, criteria=NoulCriteria(true=ANSWERS_TRUE, false=ANSWERS_FALSE + REFUSAL_IS_AN_ANSWER)),
}

if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. On our runs at 0.50: 85%. The refusals rise from 0.02 to 0.17-0.31, still below 0.50: the threshold is the next problem.")
else:
    results_v2 = client.evaluate(
        frozen_agent, data=DATASET_NAME, evaluators=[make_jev_judge(RUBRIC_V2, 0.5)],
        experiment_prefix="jev-judge-rubric-v2-refusals", max_concurrency=8,
    )
    lowest_v2 = lowest_probabilities(results_v2, RUBRIC_V2)
    agreement_by_version["Jev, rubric + refusals (0.50)"] = report(lowest_v2, 0.5)
'''),
    md('''
## 5. Pick the threshold

0.5 was a guess. A probability needs a cut-off, and choosing it is part of building the judge. Choose it on the **rule items only**, then check it on the hold-out. The experiment already holds every probability, so this costs no new calls.
'''),
    code('''
if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. On our runs the best threshold on the rule items was 0.15:")
    print("   97% overall (rule items 96%, hold-out 100%). At 0.25 it falls to 89%.")
else:
    rule_items = [i for i in lowest_v2 if i not in HOLDOUT]
    thresholds = [t / 20 for t in range(1, 20)]

    def rule_agreement(t):
        return sum((lowest_v2[i] >= t) == GOLD[i]["human_label"] for i in rule_items) / len(rule_items)

    print("Agreement on rule items:", "  ".join(f"{t:.2f}:{rule_agreement(t):.0%}" for t in thresholds[::2]))
    THRESHOLD = max(thresholds, key=lambda t: (rule_agreement(t), -abs(t - 0.5)))
    agreement_by_version[f"Jev, rubric + refusals ({THRESHOLD:.2f})"] = report(lowest_v2, THRESHOLD)
'''),
    md('''
Before trusting it, look at how close the two groups sit. Sorted by each answer's lowest question probability:
'''),
    code('''
if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. Our run's sorted scores are described below.")
else:
    for i, p in sorted(lowest_v2.items(), key=lambda kv: kv[1]):
        print(f"{p:.2f}  {'✅' if GOLD[i]['human_label'] else '❌'}  {i}")
'''),
    md('''
On our runs, every incorrect answer scored about 0.08 or lower except one, and every correct answer 0.17 or higher. The refusal fix moved the two refusals from 0.02 into that range, which is why it only shows up once the threshold is chosen. The threshold sits in a narrow gap: four correct answers (both refusals, an order report without prices, a policy answer with extra detail) score between 0.17 and 0.36, and moving the threshold to 0.25 drops agreement to 89%.

The one incorrect answer Jev passes is `sql-1`, whose itemized breakdown doesn't add up to its stated total (`facts_agree` about 0.7). Jev doesn't check arithmetic.

### 5.1 Cascade the uncertain middle

You don't have to bet on one number. Let Jev decide the answers it's confident about, and send the uncertain middle to the aligned LLM judge from Section 3, the same confidence cascade Module 4 used for routing:

```
lowest probability   < 0.10          0.10 – 0.50                 ≥ 0.50
                     incorrect       ask the aligned LLM judge   correct
                     (Jev decides)   (about 4 s per answer)      (Jev decides)
```
'''),
    code('''
from evaluators import deep_agent_correctness_evaluator

GRAY_ZONE = (0.10, 0.50)  # chosen on the rule items, like the threshold

if not JEV_AVAILABLE:
    print("⏭️  Skipped: Jev unavailable. On our runs: 4 of 33 answers went to the LLM judge, and the cascade agreed 97% (32/33).")
else:
    verdicts, sent_to_llm = {}, []
    for i, p in lowest_v2.items():
        if GRAY_ZONE[0] <= p < GRAY_ZONE[1]:
            item = GOLD[i]
            verdicts[i] = bool(deep_agent_correctness_evaluator(
                inputs={"messages": [{"role": "user", "content": item["question"]}]},
                outputs={"messages": [{"role": "assistant", "content": item["output"]}]},
                reference_outputs={"messages": [{"role": "assistant", "content": item["reference"]}]},
            )["score"])
            sent_to_llm.append(i)
        else:
            verdicts[i] = p >= GRAY_ZONE[1]
    agreement = sum(verdicts[i] == GOLD[i]["human_label"] for i in verdicts) / len(verdicts)
    agreement_by_version["Cascade: Jev + aligned LLM judge"] = agreement
    print(f"Sent {len(sent_to_llm)} of {len(verdicts)} answers to the LLM judge: {sent_to_llm}")
    print(f"Cascade agreement: {agreement:.0%}")
'''),
    md('''
## 6. Compare the judges
'''),
    code('''
if not agreement_by_version:
    print("⏭️  Skipped: Jev unavailable. Our results are in the table below.")
for version, agreement in agreement_by_version.items():
    print(f"{version:<36} {agreement:>4.0%}  {'█' * round(agreement * 30)}")
'''),
    md('''
Alongside the LLM judges from Section 3, on our runs (same 33 answers):

| Judge | Agreement | Hold-out | Time per answer | Output tokens per answer |
|---|---|---|---|---|
| LLM judge, unaligned (Sections 1–2) | 91–93% | 78–83% | about 4.4 s | about 350 |
| LLM judge, aligned (Section 3) | 97% | 100% | about 4.4 s | about 410 |
| Jev, one question (0.50) | 85–88% | 67% | about 0.2 s | — |
| Jev, rubric questions (0.15) | 97% | 100% | about 0.2 s | about 56 |
| Cascade: Jev, plus the LLM judge for 4 of 33 | 97% | — | 0.2 s for most, 4.4 s for a few | — |

Jev matched the aligned LLM judge's agreement about 20 times faster, and their single misses were different (Jev: arithmetic; the LLM judge: the mice in the keyboard total). Two cautions: 33 answers are a small benchmark, and Jev's threshold sits in a narrow gap. The cascade trades a few LLM calls for not depending on one exact number. For cost, compare the runs' usage in LangSmith; Jev bills by tokens like any model.
'''),
    md('''
## 7. The same evaluator in the LangSmith UI

LangSmith runs decision-model judges as **Decision Model Evaluators**, on a dataset (offline, like this notebook) or on a tracing project (online). The SDKs can't create them yet; use the UI or the REST endpoint `POST /api/v1/runs/rules/decision-models` ([docs](https://docs.langchain.com/langsmith/decision-model-evaluator)).

| Step | In the UI |
|---|---|
| 1. Open the evaluator | On the `techhub-deep-agent-judge-alignment` dataset: **Evaluators → + Evaluator → Decision Model Evaluator** |
| 2. Model, if your workspace has a `TYPESAFE_API_KEY` secret | Provider **TypeSafe**, model `jev-1.14.0` |
| 2. Model, with a Gateway key instead (workshop key, `LC_GATEWAY_KEY`) | **Configure prompt & model → TypeSafe-compatible endpoint**: model `typesafe/jev-1.14.0`, base URL `https://gateway.smith.langchain.com`, check **Append /v1/systemone**, no extra headers, and the Gateway key saved as a workspace secret |
| 3. State | Map the example input, the reference output, and the run output into the state, laid out as in section 2. No grading instructions |
| 4. Questions | Three **Noul** questions, `facts_agree`, `answers_question`, and `possible_actions`, with the instructions and true/false meanings from section 4 (`RUBRIC_V2`) |
| 5. Run | Each question becomes a feedback column, the same scores this notebook wrote |

The UI evaluator returns the probabilities; the threshold and the cascade stay your decision.

## 8. When to use which

| | Decision model (Jev) | LLM judge |
|---|---|---|
| Speed and cost | About 0.2 s per answer, few output tokens | Seconds per answer, reasoning tokens |
| Output | A probability per question | A verdict with a written reason |
| Good for | Grading every production trace, routing, and the confident bulk of a cascade | Nuanced or new criteria, explanations, the uncertain middle |
| Watch out for | Arithmetic and multi-step checks; thresholds that don't transfer between versions (pin `jev-1.14.0`); question wording | Cost at volume; run-to-run variance |

**Data:** TypeSafe offers zero data retention per org on request and has no BAA. TechHub is synthetic; get a security review before sending real customer data.

## Recap

- A decision-model judge is a **state** (what to judge), **questions** (the criteria, with what yes and no mean), and a **threshold**.
- Measure it against human labels exactly like an LLM judge, and fix it the same way: read the disagreements and change one question at a time.
- Choose the threshold on the rule items, check the hold-out, and look at the gap. When it's narrow, cascade the middle to an LLM judge.
- `evaluators.jev_correctness_evaluator` is the result: the three questions with a 0.15 threshold.
'''),
    code('''
from evaluators.evaluators import JEV_RUBRIC_QUESTIONS, JEV_THRESHOLD

assert {k: v.model_dump() for k, v in RUBRIC_V2.items()} == {k: v.model_dump() for k, v in JEV_RUBRIC_QUESTIONS.items()}, "evaluators/ is out of sync with this notebook"
print(f"evaluators.jev_correctness_evaluator uses these questions with threshold {JEV_THRESHOLD}.")
if JEV_AVAILABLE and THRESHOLD != JEV_THRESHOLD:
    print(f"This run picked {THRESHOLD:.2f}: probabilities move a little between runs, so check the gap before changing the saved one.")
'''),
]

# ============================================================================
# SECTION 5: Harbor evals (see docs/2026-11-12-module-5-section-3-v2-plan.md)
# ============================================================================
s5 = [
    md('''
# Module 5, Section 5: Harbor Evals

**An environment eval runs the agent in a fresh sandbox and grades what the run left behind.**

It's the same loop you've used since Module 2:

<img src="../../images/offline_eval_process.png">

[Harbor](https://www.harborframework.com/docs) swaps each part:

<img src="../../images/harbor_eval_process.svg">

| Offline eval (Module 2) | Harbor | What changes |
|---|---|---|
| **Example**: inputs and reference outputs | **Task**: a folder with the instruction, the caller's identity, a Dockerfile, and `tests/` | Each test case brings its own machine and its own checks |
| **Application**: your function, in this process | **Sandbox**: a fresh machine running the real agent with its real setup | The agent runs the way it runs in production |
| **Run**: inputs and outputs | **Run state**: every message, tool call, and tool result (`result.json`) | The grader sees what happened, not only what was said |
| **Evaluator**: `f(inputs, outputs, reference)` | **Verifier**: `verify.py(result.json)` | Plain code over the evidence; the hidden truth lives in `tests/` |
| **Experiment results** | The same LangSmith experiment | One feedback score per check |

In this section:
1. **Vocabulary**: task, environment, verifier, trial, job, reward
2. **Why**: what only the run state can show
3. **Setup**
4. **Anatomy of a task**
5. **Run a job**, and read Harbor's summary
6. **Three outcomes**: failed, errored, invalid
7. **Design a task**: a refund must wait for human approval
8. **Trust the verifier**: known answers, locally and in the sandbox
9. **Run it, then break it**
10. **Read it in LangSmith**
11. **Where this goes**
'''),
    md('''
## 1. Vocabulary

| Harbor term | What it is | Here | In LangSmith |
|---|---|---|---|
| **Task** | One test case: instruction + environment + verifier, in one folder | `managed_agent/evals/<task>/` | A dataset example |
| **Environment** | The machine the agent runs in, built from the task's Dockerfile | A LangSmith sandbox (`--env langsmith`) | The `environment-start` step of a run |
| **Verifier** | Code that reads the run state and writes the scores | `tests/verify.py` | The `verification-start` step of a run |
| **Trial** | One agent attempt at one task | One sandbox, one agent run | A run in the experiment |
| **Job** | A batch of trials across tasks | One `harbor_run(...)` call | An experiment |
| **Reward** | The verifier's scores: `reward` plus one per check | `/logs/verifier/reward.json` | Feedback columns |
'''),
    md('''
## 2. Why: what only the run state can show

A dataset evaluator grades what the agent **said**. Some properties are about what the agent **did**:

- **Side effects**: did the refund actually go out?
- **Pauses**: did the run stop for human approval?
- **Data crossing customers**: did another customer's order show up anywhere, including in a subagent's messages the customer never sees?
- **The environment**: does it work with the compiled agent, its sandbox setup, and a signed-in caller?

The refund case shows the difference. `request_refund` is the agent's only tool that changes anything, and `interrupt_on={"request_refund": True}` makes the run stop for a person to approve it:

| | ✅ Correct: paused for approval | ❌ Broken: approval removed |
|---|---|---|
| **Reply text** | None: the run paused | "I've submitted a refund request..." |
| **LLM judge on the reply** | ❌ "No answer": fail | ✅ "Helpful and polite": pass |
| **Run state** (`result.json`) | human: refund please<br>ai: `request_refund(ORD-2024-0101)`<br>`__interrupt__` ⏸ | human: refund please<br>ai: `request_refund(ORD-2024-0101)`<br>**tool: `request_refund` → "Refund submitted"** 💸<br>ai: "I've submitted..." |
| **Verifier on the run state** | ✅ reward 1 | ❌ reward 0 |

The judge is wrong both times, and the verifier is right both times, because the broken run has a `request_refund` **tool result**: the tool ran. We build this task in §7.
'''),
    md('''
## 3. Setup

Harbor runs the managed agent from Module 6, through the MDA adapter. The adapter gives each trial a verified caller from the task's `identity.json`, the way a signed-in customer's token would. (For a plain Deep Agent with no identity, Harbor's built-in `--agent langgraph` does the same job; see [Harbor integrations](https://docs.langchain.com/langsmith/harbor-integrations).)

You need `uv`, `LANGSMITH_API_KEY`, and model access (a provider key, or `LANGSMITH_GATEWAY_API_KEY`; see the README). `--env langsmith` runs trials in LangSmith sandboxes, so you don't need Docker. The next cell prepares the managed agent's eval runner if it isn't ready yet.

The helpers in `utils/harbor_runs.py` wrap the command from `managed_agent/evals/README.md`, show a live progress panel, and read results back.
'''),
    code('''
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

from utils.harbor_runs import DATASET, PROJECT, harbor_run, harbor_summary, mda_runner_ready, results_table, uv_env

EVALS = PROJECT / "evals"

assert shutil.which("uv"), "Install uv: https://docs.astral.sh/uv/"
assert os.environ.get("LANGSMITH_API_KEY"), "Set LANGSMITH_API_KEY in .env"
model_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_GATEWAY_API_KEY", "LANGSMITH_API_KEY_GATEWAY", "LC_GATEWAY_KEY"]
assert any(os.environ.get(k) for k in model_keys), f"Set one of {model_keys} in .env (see the README)"

if not mda_runner_ready():
    for argv in (["uv", "sync", "--python", "3.14"], ["uv", "run", "mda", "evals", "init"]):
        print("$", " ".join(argv))
        subprocess.run(argv, cwd=PROJECT, env=uv_env(), check=True)
print("MDA eval runner ready:", mda_runner_ready())
'''),
    md('''
## 4. Anatomy of a task

```
order-status-own-order/
├── instruction.md     → the user's message
├── identity.json      → who is asking: signed-in customer CUST-003
├── task.toml          → timeouts, CPU and memory, env vars
├── environment/
│   └── Dockerfile     → the machine the agent runs in
├── tests/
│   ├── test.sh        → what Harbor runs after the agent stops
│   ├── verify.py      → the checks: plain Python, no LLM judge
│   └── mda_result.py  → shared helper: reads the run state, writes the scores
└── Task.md            → the spec, for people; the agent never sees it
```

The input and the verifier for one task:
'''),
    code('''
task = EVALS / "order-status-own-order"
print("--- instruction.md\\n" + (task / "instruction.md").read_text())
print("--- identity.json\\n" + (task / "identity.json").read_text())
print("--- tests/verify.py\\n" + (task / "tests/verify.py").read_text())
'''),
    md('''
`report()` prints each check and writes `reward.json`: the overall `reward` plus one score per check. `test.sh` deletes any reward file before `verify.py` runs, because the agent ran in the same machine and could have left one behind.
'''),
    md('''
## 5. Run a job

The managed agent ships with three tasks, each checking one property:

| Task | The customer asks | Passes when |
|---|---|---|
| `order-status-own-order` | About their own order | The answer says "Shipped" and gives the right tracking number (correctness) |
| `cross-customer-order-refused` | About another customer's order | Nothing from that order appears anywhere in the run (authorization) |
| `opened-item-return-window` | Whether an opened keyboard can be returned after 20 days | The answer cites the 14-day window and says no (grounding) |

One job runs all three as parallel trials, about 3 minutes:

```
harbor_run(EXISTING, ...)        one job
  │
  ├─ MDA plugin compiles managed_agent/agent.py once
  │
  ├─ trial: order-status     ┐
  ├─ trial: cross-customer   ├─ each in its own sandbox:
  └─ trial: opened-item      ┘    start machine → install agent → run instruction.md
                                  as identity.json → save result.json → verify.py → reward.json
  │
  └─ LangSmith plugin: one experiment, one run per trial, one feedback score per reward key
```
'''),
    code('''
EXISTING = ["order-status-own-order", "cross-customer-order-refused", "opened-item-return-window"]

job, experiment = harbor_run(EXISTING, "m5-existing-tasks")
'''),
    md('''
**Harbor's summary**, as `harbor run` prints it in a terminal. The first table has one column per reward key, each the **mean over trials** (names are cut to fit). The second counts trials by score for each key, without labels:
'''),
    code('''
harbor_summary(experiment)
'''),
    md('''
Read the means carefully. `Reward` is 1.000 because all three tasks passed. But each check column belongs to **one** task, and Harbor averages it over all three trials, so a check that passed shows **0.333**. Per task, read back from the LangSmith experiment:
'''),
    code('''
results_table(experiment)
'''),
    md('''
## 6. Three outcomes

A score of 0 doesn't always mean the agent failed:

| Outcome | What happened | Whose problem | How it shows |
|---|---|---|---|
| **Failed** | The verifier ran and a check failed | The agent (or the task measured the wrong thing) | `reward` 0, and the failing check is 0 |
| **Errored** | The sandbox, the runner, or a timeout failed before scoring | Infrastructure: fix it and rerun | `harbor_error` feedback (⚠️ in the panel and the table) |
| **Invalid** | The verifier found no evidence (no `result.json`) | Neither: rerun | `reward` 0 plus `invalid` 1 |

Count only **failed** trials against the agent.
'''),
    md('''
## 7. Design a task: a refund must wait for human approval

The task from §2. What should happen, and what a broken agent does:

```
Customer (CUST-003): "My LG monitor from ORD-2024-0101 died. Refund please."
        │
        ▼
   main agent ──► request_refund(order_id="ORD-2024-0101")
                        │
            ┌───────────┴───────────────┐
            ▼                           ▼
   approval check (interrupt_on)    no approval check (broken)
   ⏸ run pauses, tool does NOT run  💸 refund runs immediately
   no final answer                  "Yes — I've submitted a refund request..."
```

Design it spec-first, the way the [`eval-engineering` skill](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/eval-engineering/SKILL.md) recommends. The spec says what passes before any code exists, from facts in the database: `ORD-2024-0101` belongs to `CUST-003`, was delivered, and holds one LG 24" monitor.
'''),
    code('''
refund_task = EVALS / "refund-requires-approval"
print((refund_task / "Task.md").read_text())
'''),
    md('''
The input names the order and asks for a refund explicitly, so a correct agent always gets as far as requesting it. The caller is signed in as `CUST-003`:
'''),
    code('''
print("--- instruction.md\\n" + (refund_task / "instruction.md").read_text())
print("--- identity.json\\n" + (refund_task / "identity.json").read_text())
'''),
    md('''
### The verifier

Two checks, both on the run state:

```
result.json
   ├── R1: an ai message calls request_refund with order_id "ORD-2024-0101"
   │       (without this, an agent that refuses to help would pass)
   └── R2: no tool message named request_refund
           (a result means the tool ran: the pause didn't hold)

reward = 1 only if R1 and R2 both pass
```

> 💡 **Try it first:** write R1 and R2 yourself with `tool_calls(messages)` and `role_of(m)` from `mda_result.py`, then compare with the verifier below.
'''),
    code('''
print((refund_task / "tests/verify.py").read_text())
'''),
    md('''
## 8. Trust the verifier

A wrong verifier is worse than none: it reports pass, and nobody looks again. Before trusting its scores, check it against answers you already know.

| | Local fixtures | Oracle |
|---|---|---|
| What runs | `verify.py` on hand-made run states | Harbor's built-in `oracle` agent, which runs the task's `solution/solve.sh` instead of a model |
| Where | Your machine | A real sandbox, through `test.sh` |
| Checks | The verifier's logic, good and bad cases | The whole task: Dockerfile, `test.sh`, verifier |
| Cost | About a second | About 10 seconds, no model calls |

**Local fixtures.** The verifier reads its paths from environment variables, so it runs here as-is. One known-good state and one known-bad:
'''),
    code('''
QUESTION = {"type": "human", "content": (refund_task / "instruction.md").read_text()}
REFUND_CALL = {"type": "ai", "content": "", "tool_calls": [{"name": "request_refund", "args": {"order_id": "ORD-2024-0101"}, "id": "call_1"}]}
FIXTURES = {
    "paused for approval (expect pass)": {"messages": [QUESTION, REFUND_CALL], "__interrupt__": [{"value": "approve?"}]},
    "refund ran (expect fail)": {"messages": [
        QUESTION, REFUND_CALL,
        {"type": "tool", "name": "request_refund", "content": "Refund request REF-1 submitted"},
        {"type": "ai", "content": "I've submitted your refund request."},
    ]},
}

for outcome, state in FIXTURES.items():
    with tempfile.TemporaryDirectory() as tmp:
        result = os.path.join(tmp, "result.json")
        with open(result, "w") as f:
            json.dump(state, f)
        env = {**os.environ, "MDA_EVAL_RESULT": result, "MDA_EVAL_INVALID": os.path.join(tmp, "invalid.txt"), "MDA_EVAL_REWARD": os.path.join(tmp, "reward.json")}
        run = subprocess.run([sys.executable, str(refund_task / "tests/verify.py")], env=env, capture_output=True, text=True)
    print(f"▶ {outcome}\\n{run.stdout}")
'''),
    md('''
**The oracle.** `solution/solve.sh` writes the run state a correct agent leaves behind. If the oracle doesn't score 1, the task itself is broken, before any model is involved:
'''),
    code('''
print((refund_task / "solution/solve.sh").read_text())

job, oracle_experiment = harbor_run(["refund-requires-approval"], "m5-refund-oracle", agent="oracle")
harbor_summary(oracle_experiment)
'''),
    md('''
## 9. Run it, then break it

Now the real agent, about 2 minutes. Expect reward 1 and **no final answer**: the run paused for approval.
'''),
    code('''
job, approval_experiment = harbor_run(["refund-requires-approval"], "m5-refund-approval")
results_table(approval_experiment)
'''),
    md('''
A task that has never failed hasn't shown it can catch anything. Remove the approval step from `agent.py`, the way a careless refactor might, and run again. The cell restores `agent.py` when the run ends, even if it fails.
'''),
    code('''
agent_py = PROJECT / "agent.py"
original = agent_py.read_text()
APPROVAL = 'interrupt_on={"request_refund": True},'
assert original.count(APPROVAL) == 1, "agent.py changed: find the interrupt_on line by hand"

agent_py.write_text(original.replace(APPROVAL, "interrupt_on={},"))
try:
    job, no_approval_experiment = harbor_run(["refund-requires-approval"], "m5-refund-no-approval")
finally:
    agent_py.write_text(original)
assert agent_py.read_text() == original
print("agent.py restored\\n")
results_table(no_approval_experiment)
'''),
    md('''
| | Approval on | Approval removed |
|---|---|---|
| `requested_a_refund_for_ord_2024_0101` | ✅ 1 | ✅ 1 |
| `refund_never_ran_without_approval` | ✅ 1 | ❌ **0**: the regression |
| `reward` | ✅ 1 | ❌ 0 |
| Final answer | None: paused | "Yes — I've submitted a refund request..." |

The per-check scores say exactly what broke. When a task fails, decide which side is wrong: if it measured the wrong thing, fix the task; if it caught a real problem, fix the agent.

If you see `harbor_error` instead (for example, "Agent setup timed out"), the sandbox failed before the agent ran: that's the **errored** outcome from §6, not a result. Rerun the cell.
'''),
    md('''
## 10. Read it in LangSmith

```
Harbor                              LangSmith
──────                              ─────────
evals/ (the tasks)           ──►    dataset   m5-harbor-techhub-support
  each task                  ──►      example
harbor_run(...) (a job)      ──►    experiment
  each trial                 ──►      run, with steps environment-start,
                                      agent-start, verification-start
  reward.json keys           ──►        feedback columns
  trial crashed              ──►        harbor_error feedback
```

Compare the approved and broken runs: open the link, select the `refund-requires-approval` example, and look at the feedback columns.
'''),
    code('''
client = Client()
dataset = client.read_dataset(dataset_name=DATASET)
compare = [client.read_project(project_name=name) for name in (approval_experiment, no_approval_experiment)]
print("📊 Dataset:", dataset.url)
print("📊 Compare:", f"{dataset.url}/compare?selectedSessions={','.join(str(e.id) for e in compare)}")
'''),
    md('''
> ⚠️ For managed agent runs, Harbor doesn't record token counts or cost yet (`tokens` and `cost_usd` are empty on each run).

## 11. Where this goes

**From evaluation to training.** A verifier's reward is a training signal too. The same tasks can drive reinforcement learning or rejection-sampled fine-tuning, and Harbor records every trial's full trajectory. Per-check scores give partial credit, and many task variations stop a model from memorizing one answer.

**Harbor tasks or dataset evaluators?**

```
                    What are you checking?
                            │
       ┌────────────────────┴────────────────────┐
       ▼                                         ▼
 How good is the answer?               Did something happen (or not)?
 (correct, complete, grounded)         (side effect, approval pause, data
       │                                crossing customers, the real setup)
       ▼                                         ▼
 Dataset evaluator                       Harbor task
 many examples, seconds each             a few tasks, minutes each
       └──────────────────┬──────────────────────┘
                          ▼
         run both before release: dataset evals show whether quality
         moved; Harbor tasks block a release that breaks what must never break
```

## Recap

- An environment eval runs the agent in a fresh sandbox and grades the run state, not just the reply.
- A task is a folder: instruction, identity, environment, and a verifier that is plain code.
- One score per check makes a failure explain itself. Failed, errored, and invalid are different outcomes.
- Write the spec first, then trust the verifier only after it passes known answers: local fixtures, then the oracle.
- Break the agent on purpose once. A task that has never failed hasn't shown it can catch anything.
'''),
]

save("section_1_baseline_evaluation.ipynb", s1)
save("section_2_eval_driven_development.ipynb", s2)
save("section_3_align_llm_judge.ipynb", s3)
save("section_4_jev_as_judge.ipynb", s4)
save("section_5_harbor_evals.ipynb", s5)
