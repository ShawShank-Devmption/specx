"""Define agent-visible tools and dispatch calls through the sandbox boundary.

Observe exposes only URL/ARIA, not the privileged database used by success checks.
"""

import json
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator

from specx.client import SandboxClient, SandboxError
from specx.evalx.conditions import Condition


class BadToolArgumentsError(ValueError):
    pass


def model_tools(tools: list[dict[str, Any]], condition: Condition) -> list[dict[str, Any]]:
    exposed = [
        {key: deepcopy(tool[key]) for key in ("name", "description", "input_schema")}
        for tool in tools
    ]
    helper_specs = [
        ("observe", "Observe the current page's URL and ARIA snapshot with element refs.", {}),
        (
            "finish",
            "Finish when done or when the task is impossible; summarize the outcome.",
            {"summary": {"type": "string"}},
        ),
    ]
    if condition == Condition.raw_dom:
        helper_specs.extend(
            [
                (
                    "click",
                    "Click an element using its current ARIA ref.",
                    {"ref": {"type": "string"}},
                ),
                (
                    "type",
                    "Fill an input using its current ARIA ref.",
                    {"ref": {"type": "string"}, "text": {"type": "string"}},
                ),
                (
                    "navigate",
                    "Navigate to a path in the current application.",
                    {"path": {"type": "string"}},
                ),
            ]
        )
    for name, description, properties in helper_specs:
        exposed.append(
            {
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        )
    for tool in exposed:
        Draft202012Validator.check_schema(tool["input_schema"])
        if tool["input_schema"].get("type") != "object":
            raise ValueError(f"Agent tool {tool['name']} requires an object input schema")
        tool["strict"] = True
    exposed[-1]["cache_control"] = {"type": "ephemeral"}
    return exposed


def parse_input(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise BadToolArgumentsError(f"Invalid tool input JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise BadToolArgumentsError("Tool input must be a JSON object")
    return value


def dispatch(
    client: SandboxClient,
    session_id: str,
    name: str,
    args: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
    exposed: list[dict[str, Any]],
    condition: Condition,
) -> tuple[Any, dict[str, Any] | None, bool]:
    if name in by_name:
        verdict = client.invoke(session_id, by_name[name]["tool_id"], args, source="f4")
        return {"status": verdict["status"], "output": verdict.get("output")}, verdict, False
    definition = next((tool for tool in exposed if tool["name"] == name), None)
    if definition is None:
        raise SandboxError("unknown_tool", name)
    error = next(Draft202012Validator(definition["input_schema"]).iter_errors(args), None)
    if error:
        raise BadToolArgumentsError(error.message)
    if name == "finish":
        return {"ok": True, "summary": args["summary"]}, None, True
    if name == "observe":
        state = client.state(session_id)
        return {"url": state["url"], "aria": state["aria"]}, None, False
    if condition != Condition.raw_dom:
        raise SandboxError("unknown_tool", name)
    body = {"url": args["path"]} if name == "navigate" else args
    return client.dom_action(session_id, name, **body), None, False
