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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
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
| `order_specialist_tool_calls` | Long chains of rigid lookups: `get_customer_orders` → `get_order_items` per order → `get_order_item_price` per item. Totals and counts get added up in the model's head |
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
from dotenv import load_dotenv
from tools.database import query_my_orders

load_dotenv()

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
    code('''
import inspect

print(inspect.getsource(query_my_orders.func))
'''),
    md('''
Now an agent that writes those queries, using the `create_agent()` abstraction with the same context schema as the deep agent:
'''),
    code('''
from langchain.agents import create_agent
from agents.deep_support_agent import SupportContext
from config import DEFAULT_MODEL

sql_agent = create_agent(
    model=DEFAULT_MODEL,
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

Some answers will still be marked wrong for adding detail or masking data for privacy. That's the judge, not the agent: aligning the judge is next.
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
save("section_5_harbor_evals.ipynb", s5)
