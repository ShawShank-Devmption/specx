"""Validated failure evidence records for optimisation and later S4 dataset export.

Synthetic injections carry explicit provenance and never claim observed executions.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from specx.client.schemas import validate

Mutation = Literal["misleading_description", "renamed_param", "broken_selector"]


class FailureBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    trial_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    tool_ids: list[str]
    tools: list[dict[str, Any]]
    transcript_tail: list[dict[str, Any]] = Field(max_length=6)
    verdicts: list[dict[str, Any]]
    aria_before: str
    aria_after: str
    dom_diff: str = Field(max_length=4000)
    network_log: list[dict[str, Any]]
    screenshot_b64: str | None
    failure_reason: str
    split: Literal["train", "heldout"] | None = None
    synthetic: bool = False
    synthetic_mutation: Mutation | None = None

    @model_validator(mode="after")
    def check_evidence(self) -> Self:
        for tool in self.tools:
            validate("tool_definition", tool)
        for verdict in self.verdicts:
            validate("verdict", verdict)
        if self.tool_ids != [tool["tool_id"] for tool in self.tools] or len(
            set(self.tool_ids)
        ) != len(self.tool_ids):
            raise ValueError("Bundle tool_ids must match its unique tool definitions in order")
        if self.synthetic != (self.synthetic_mutation is not None):
            raise ValueError("Synthetic bundles must identify their mutation explicitly")
        if self.synthetic and (
            self.verdicts or self.network_log or self.screenshot_b64 is not None
        ):
            raise ValueError(
                "Synthetic injections cannot claim observed verdicts, requests or screenshots"
            )
        for message in self.transcript_tail:
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_result"
                        and isinstance(block.get("content"), str)
                        and len(block["content"]) > 2000
                    ):
                        raise ValueError(
                            "Bundle tool_result bodies must be at most 2000 characters"
                        )
        return self
