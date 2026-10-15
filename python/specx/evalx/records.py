"""Typed trial, tool-step and trace records constructed by the evaluation harness.

Cache accounting lives in the trace because the shared trial schema has no cache fields.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from specx.client.schemas import validate
from specx.evalx.llm import Usage

ViolationKind = Literal[
    "forbidden_action",
    "unconfirmed_destructive",
    "unapproved_endpoint",
    "scope_exceeded",
    "quarantined_tool",
]


class PolicyViolation(BaseModel):
    kind: ViolationKind
    detail: str
    step: int | None = None


class TrialResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    trial_id: str
    app: str
    condition: str
    task_id: str
    split: str
    seed: int
    agent_model: str
    tool_set_version: str
    success: bool
    steps: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    wall_ms: float = Field(ge=0)
    policy_violations: list[PolicyViolation]
    quarantined_tool_calls: int = Field(ge=0)
    unapproved_calls: int = Field(ge=0)
    failure_reason: str
    timestamp: str
    revision_id: str | None = None

    def record(self) -> dict[str, Any]:
        record = self.model_dump(exclude_none=True)
        validate("trial_result", record)
        return record


class ToolStep(BaseModel):
    step: int
    name: str
    tool_use_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    tool_id: str | None = None
    risk_level: str | None = None
    tool_status: str | None = None
    invoked: bool = False
    condition: str
    app_url: str
    url_before: str
    url_after: str = ""
    aria_before: str
    aria_after: str = ""
    attempted_url: str | None = None
    error_code: str | None = None
    error: str | None = None
    verdict_run_id: str | None = None
    event_seqs: list[int] = Field(default_factory=list)


class EpisodeTrace(BaseModel):
    trial_id: str
    task_id: str
    app: str
    condition: str
    seed: int
    session_id: str
    agent_model: str
    tool_set_version: str
    system: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    responses: list[dict[str, Any]] = Field(default_factory=list)
    step_log: list[dict[str, Any]] = Field(default_factory=list)
    verdicts: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    aria_before: str = ""
    aria_after: str = ""
    final_screenshot_b64: str | None = None
    stop_reason: str = "max_steps"
