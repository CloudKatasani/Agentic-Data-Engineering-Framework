from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..workspace.run import RunWorkspace
from .agent_runtime import AgentCall


@dataclass
class StageOutput:
    artifacts: list[str]
    summary: str
    gate_meta: dict = field(default_factory=dict)       # risk, cost, rollback, options, extra_roles
    assumptions: list[dict] = field(default_factory=list)
    open_questions: list[dict] = field(default_factory=list)
    risks: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    requirement_ids: list[str] = field(default_factory=list)
    inputs_used: list[str] = field(default_factory=list)
    confidence: tuple[str, str] = ("medium", "")
    request_gate: bool = True


@dataclass
class StageCtx:
    ws: RunWorkspace
    call: AgentCall
    scenario: dict
    log: Callable[[str], None]
    feedback: str | None = None
    settings: dict = field(default_factory=dict)

    @property
    def agent(self) -> str:
        return self.call.agent

    def write(self, rel: str, content: str, **kw) -> str:
        self.ws.write(self.agent, rel, content, **kw)
        self.log(f"{self.agent} wrote {rel}")
        return rel

    def q(self, id_: str, question: str, ask: str, blocking: bool = False) -> dict:
        return {"id": id_, "question": question, "blocking": blocking, "ask_whom": ask}

    def a(self, id_: str, text: str, impact: str, owner: str) -> dict:
        return {"id": id_, "text": text, "impact_if_wrong": impact, "owner_to_confirm": owner}

    def r(self, id_: str, text: str, likelihood: str, impact: str, mitigation: str) -> dict:
        return {"id": id_, "text": text, "likelihood": likelihood, "impact": impact, "mitigation": mitigation}
