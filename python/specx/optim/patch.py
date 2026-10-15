"""Apply validated, revision-bound metadata edits without mutating source tools."""

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator

from specx.client.schemas import validate


class StalePatchError(ValueError):
    pass


StalePatch = StalePatchError


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a nonempty string")
    return value


def apply_patch(tool: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    validate("tool_definition", tool)
    validate("patch", patch)
    if patch["tool_id"] != tool["tool_id"]:
        raise ValueError("Patch targets a different tool")
    if patch["base_metadata_revision"] != tool["metadata_revision"]:
        raise StalePatch("Patch base_metadata_revision is stale")
    result = deepcopy(tool)
    for operation in patch["ops"]:
        op, value = operation["op"], operation.get("value")
        if op == "rename":
            result["name"] = _text(value)
        elif op == "set_description":
            result["description"] = _text(value)
        elif op == "fix_selector":
            old, new = _text(operation.get("old_value")), _text(value)
            handler = result["handler"]
            if handler["kind"] != "ui":
                raise ValueError("fix_selector is restricted to UI handlers")
            if old not in handler.get("selectors", []) or old not in handler.get("code", ""):
                raise ValueError("Selector must exist in both selectors and handler code")
            handler["selectors"] = [new if item == old else item for item in handler["selectors"]]
            handler["code"] = handler["code"].replace(old, new)
        else:
            schema = result["input_schema"]
            param = operation.get("param")
            if not isinstance(param, str) or param not in schema.get("properties", {}):
                raise ValueError("Parameter operation targets an unknown property")
            prop = schema["properties"][param]
            if op == "set_param_description":
                prop["description"] = _text(value)
            elif op == "add_enum":
                if not isinstance(value, list) or not value:
                    raise ValueError("add_enum requires a nonempty array")
                enum = prop.setdefault("enum", [])
                for item in value:
                    if item not in enum:
                        enum.append(deepcopy(item))
            elif op == "set_example":
                if "value" not in operation:
                    raise ValueError("set_example requires value")
                prop["examples"] = [deepcopy(value)]
            elif op == "mark_required":
                required = schema.setdefault("required", [])
                if param not in required:
                    required.append(param)
    result["metadata_revision"] += 1
    Draft202012Validator.check_schema(result["input_schema"])
    validate("tool_definition", result)
    return result
