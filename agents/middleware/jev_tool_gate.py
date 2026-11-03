"""Jev tool-safety gate: a decision model screens tool calls for side effects (Module 4 S3).

Deterministic `interrupt_on` stays the control for tools you know are dangerous
(`request_refund`). This gate covers the long tail: before any other tool runs, Jev
answers one yes/no question about the call, and calls likely to change something are
paused for a human, using the same approve/reject payload as `interrupt_on`.

Pattern from langchain-samples/langchain-typesafe-demos (ToolSafetyGateMiddleware), with
the scoring moved to `after_model` (as `HumanInTheLoopMiddleware` records its edits):

- Scores are computed once, when the model proposes the calls, and kept in state. A resumed
  tool call reads the stored score, so a reviewer's "reject" can't be bypassed by Jev scoring
  the call differently the second time.
- Fails closed: if Jev can't be reached, the call goes to a human instead of running.
- Parallel tool calls each pause separately: resume them by interrupt id.
- Not an access control: the customer-scope guard still decides who may see what.
"""

from typing import Annotated, Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState, PrivateStateAttr
from langchain_core.messages import AIMessage, ToolMessage
from langchain_typesafe import Noul, NoulCriteria, TypeSafeClassifier
from langgraph.types import interrupt
from typing_extensions import NotRequired

SIDE_EFFECT = Noul(
    instructions="Would running this tool call change data, move money, or affect someone outside this conversation?",
    criteria=NoulCriteria(
        true="It writes, edits, or deletes records or files, sends something, or starts a payment or refund.",
        false="It only reads, lists, or searches, or writes to the agent's own scratch notes.",
    ),
)


class JevGateState(AgentState):
    jev_scores: NotRequired[Annotated[dict[str, float | None], PrivateStateAttr]]
    """Side-effect score per tool call id, from the latest model turn (None = Jev unavailable)."""


class JevToolGate(AgentMiddleware):
    """Pause tool calls that Jev scores as likely side effects, for human approval."""

    state_schema = JevGateState

    def __init__(self, classifier: TypeSafeClassifier | None = None, threshold: float = 0.5, skip=()):
        super().__init__()
        self._classifier = classifier
        self.threshold = threshold
        self.skip = set(skip)

    @property
    def classifier(self) -> TypeSafeClassifier:
        if self._classifier is None:  # built on first use, so importing needs no credentials
            from utils.jev import jev_classifier

            self._classifier = jev_classifier()
        return self._classifier

    @staticmethod
    def _input(name: str, args: dict) -> dict:
        return {"state": {"tool": name, "arguments": args}, "questions": {"side_effect": SIDE_EFFECT}}

    def score(self, name: str, args: dict) -> float:
        """Probability that the call has a side effect."""
        return self.classifier.invoke(self._input(name, args)).nouls["side_effect"].noul

    async def ascore(self, name: str, args: dict) -> float:
        return (await self.classifier.ainvoke(self._input(name, args))).nouls["side_effect"].noul

    def _calls_to_score(self, state) -> list[dict]:
        last = state["messages"][-1] if state.get("messages") else None
        if not isinstance(last, AIMessage):
            return []
        return [c for c in last.tool_calls if c["name"] not in self.skip]

    # Score once, when the model proposes the calls
    def after_model(self, state, runtime) -> dict[str, Any] | None:
        calls = self._calls_to_score(state)
        if not calls:
            return None
        try:
            answers = self.classifier.batch([self._input(c["name"], c.get("args") or {}) for c in calls], return_exceptions=True)
        except Exception as e:
            answers = [e] * len(calls)
        return {"jev_scores": self._scores(calls, answers)}

    async def aafter_model(self, state, runtime) -> dict[str, Any] | None:
        calls = self._calls_to_score(state)
        if not calls:
            return None
        try:
            answers = await self.classifier.abatch(
                [self._input(c["name"], c.get("args") or {}) for c in calls], return_exceptions=True
            )
        except Exception as e:
            answers = [e] * len(calls)
        return {"jev_scores": self._scores(calls, answers)}

    @staticmethod
    def _scores(calls: list[dict], answers: list) -> dict[str, float | None]:
        return {c["id"]: None if isinstance(a, BaseException) else a.nouls["side_effect"].noul for c, a in zip(calls, answers)}

    # Decide from the stored score, so a resumed call sees the same score
    def _review(self, request) -> ToolMessage | None:
        """Return a rejection message, or None to let the call run."""
        call = request.tool_call
        scores = (request.state or {}).get("jev_scores") or {}
        score = scores.get(call["id"])  # missing (not scored this turn) is treated like unavailable
        if score is not None and score <= self.threshold:
            return None
        reason = f"Jev side-effect score {score:.2f} > {self.threshold:.2f}" if score is not None else "Jev score unavailable"
        decision = interrupt(
            {
                "action_requests": [{"name": call["name"], "args": call["args"], "description": f"{reason}. Approve?"}],
                "review_configs": [{"action_name": call["name"], "allowed_decisions": ["approve", "reject"]}],
            }
        )
        if decision["decisions"][0]["type"] == "approve":
            return None
        return ToolMessage(
            content="A reviewer rejected this tool call.", tool_call_id=call["id"], name=call["name"], status="error"
        )

    def wrap_tool_call(self, request, handler):
        if request.tool_call["name"] in self.skip:
            return handler(request)
        return self._review(request) or handler(request)

    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] in self.skip:
            return await handler(request)
        return self._review(request) or await handler(request)
