"""Validate boundary records with the repository's cached draft-2020-12 schemas.

Errors include an escaped JSON pointer so both Python consumers can locate bad fields.
"""

import json
from functools import cache

from jsonschema import Draft202012Validator, FormatChecker

from specx.client.paths import repo_root


@cache
def _validator(name: str) -> Draft202012Validator:
    schemas = repo_root() / "contracts"
    if name not in {p.name.removesuffix(".schema.json") for p in schemas.glob("*.schema.json")}:
        raise ValueError(f"Unknown schema: {name!r}")
    schema = json.loads((schemas / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name: str, obj: object) -> None:
    error = next(_validator(name).iter_errors(obj), None)
    if error is not None:
        pointer = "/" + "/".join(
            str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path
        )
        raise ValueError(f"{name}{pointer}: {error.message}")
