"""Select condition-specific tool sets without changing their handlers or metadata.

Versions include a stable content digest so different candidates cannot share an ID.
"""

import hashlib
import json
from copy import deepcopy
from enum import StrEnum
from typing import Any

from specx.client.io import read_json
from specx.client.paths import tools_path
from specx.client.schemas import validate


class Condition(StrEnum):
    raw_dom = "raw_dom"
    generated = "generated"
    verified = "verified"
    optimised = "optimised"


def select_tools(
    app: str, tools: list[dict[str, Any]], condition: Condition
) -> list[dict[str, Any]]:
    if condition == Condition.raw_dom:
        return []
    selected = []
    names: set[str] = {"observe", "finish"}
    ids: set[str] = set()
    for tool in tools:
        validate("tool_definition", tool)
        if tool["app"] != app:
            raise ValueError(f"Tool {tool['tool_id']} does not belong to {app}")
        if condition != Condition.generated and tool.get("status") != "verified":
            continue
        if tool["name"] in names or tool["tool_id"] in ids:
            raise ValueError(f"Duplicate or reserved tool name/id: {tool['name']}")
        names.add(tool["name"])
        ids.add(tool["tool_id"])
        selected.append(deepcopy(tool))
    return selected


def tool_set_version(app: str, tools: list[dict[str, Any]], condition: Condition) -> str:
    if condition == Condition.raw_dom:
        return "none"
    if not tools:
        return f"{app}@empty"
    encoded = json.dumps(
        sorted(tools, key=lambda tool: tool["tool_id"]),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:12]
    version = max(tool["version"] for tool in tools)
    revision = max(tool["metadata_revision"] for tool in tools)
    return f"{app}@v{version}.r{revision}.{digest}"


def tool_set_for(
    app: str, condition: Condition, arm: str | None = None
) -> tuple[list[dict[str, Any]], str]:
    condition = Condition(condition)
    if condition == Condition.raw_dom:
        return [], "none"
    if condition == Condition.optimised:
        if arm not in ("text_trace", "text_structured", "multimodal_structured"):
            raise ValueError("Optimised condition requires an explicit valid arm")
        path = tools_path(app, f"optimised.{arm}")
    else:
        path = tools_path(app)
    records = read_json(path)
    if not isinstance(records, list):
        raise ValueError(f"Expected a tool array in {path}")
    tools = select_tools(app, records, condition)
    return tools, tool_set_version(app, tools, condition)
