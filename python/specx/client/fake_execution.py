"""Canned invocation checks, events and one-shot leaks for the offline sandbox.

These helpers model only the named C1 cases, not arbitrary executable contracts.
"""

import json
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin, urlsplit

from specx.client.fake_records import ClauseResult, EventRecord, Verdict, fail
from specx.client.fake_state import FakeSession, next_id, perform, product


def emit_event(
    session: FakeSession,
    verdict: Verdict,
    kind: str,
    data: dict[str, Any],
    *,
    t_ms: float,
    phase: str = "during",
) -> None:
    session.events.append(
        EventRecord(
            session_id=verdict.session_id,
            run_id=verdict.run_id,
            seq=len(session.events),
            t_ms=t_ms,
            phase=phase,
            kind=kind,
            data=data,
        ).record()
    )


def network_event(network: dict[str, Any], request_id: str, body_bytes: int) -> dict[str, Any]:
    """Provide the fields S6's feature windower expects on network requests."""
    return {
        **network,
        "request_id": request_id,
        "host": urlsplit(network["url"]).netloc,
        "body_bytes": body_bytes,
        "initiator": "fetch",
    }


def precheck(
    session: FakeSession, tool: dict[str, Any], action: str, args: dict[str, Any], verdict: Verdict
) -> bool:
    schema = tool["input_schema"]
    if any(param not in args for param in schema.get("required", [])):
        fail(
            verdict,
            "pre_required_args",
            "output_matches",
            "precondition",
            "missing args",
            "required args",
            surface="code",
        )
        return False
    for param, spec in schema.get("properties", {}).items():
        if param not in args:
            continue
        value, kind = args[param], spec.get("type")
        invalid = (
            (kind == "integer" and type(value) is not int)
            or (kind == "boolean" and type(value) is not bool)
            or (kind == "string" and not isinstance(value, str))
        )
        if invalid:
            verdict.status = "error"
            return False
    if "product_id" in args and product(session, args["product_id"]) is None:
        fail(
            verdict,
            "pre_product_exists",
            "db_row_exists",
            "precondition",
            "missing product",
            "existing product",
        )
        return False
    if action == "add_to_cart" and args["qty"] < 1:
        fail(
            verdict,
            "pre_qty_positive",
            "output_matches",
            "precondition",
            args["qty"],
            ">=1",
            surface="code",
        )
        return False
    if action == "place_order":
        if args.get("confirm") is not True:
            fail(
                verdict,
                "pre_confirm",
                "output_matches",
                "precondition",
                False,
                True,
                surface="code",
            )
            return False
        if not session.db["cart_items"]:
            fail(
                verdict,
                "pre_cart_nonempty",
                "db_row_exists",
                "precondition",
                "empty cart",
                "nonempty cart",
            )
            return False
    return True


def execute(
    session: FakeSession, verdict: Verdict, tool: dict[str, Any], action: str, args: dict[str, Any]
) -> None:
    verdict.output, audit = perform(session, action, args)
    http = tool.get("handler", {}).get("http")
    if http:
        path = http["path_template"]
        for key, value in args.items():
            path = path.replace("{" + key + "}", str(value))
        network = {
            "method": http["method"],
            "url": urljoin(session.url, path),
            "approved": True,
            "third_party": False,
            "status": 200,
            "phase": "during",
        }
        verdict.effect_diff.network.append(network)
        emit_event(
            session,
            verdict,
            "network_request",
            network_event(network, verdict.run_id, len(json.dumps(args).encode())),
            t_ms=12,
        )
        emit_event(
            session,
            verdict,
            "network_response",
            {
                "request_id": verdict.run_id,
                "status": 200,
                "body_bytes": 44,
                "mime": "application/json",
            },
            t_ms=41,
        )
    if audit:
        session.db["audit_log"].append(
            {
                "id": next_id(session.db["audit_log"]),
                "event": audit,
                "actor": "alice",
                "entity": action,
                "entity_id": "1",
                "ts": verdict.started_at,
            }
        )
        verdict.effect_diff.audit.append({"event": audit, "count": 1})
        verdict.effect_diff.dom["mutations"] = 1
        emit_event(
            session,
            verdict,
            "audit",
            {"event": audit, "actor": "alice", "entity": action, "entity_id": "1"},
            t_ms=43,
        )
        emit_event(
            session,
            verdict,
            "dom_mutation",
            {
                "added": 1,
                "removed": 0,
                "attr_changed": 1,
                "text_changed": 1,
                "target_selector": "[data-testid=cart-count]",
            },
            t_ms=48,
        )
    for contract in session.contracts:
        if contract["tool_id"] == tool["tool_id"]:
            for section in ("preconditions", "postconditions", "invariants"):
                for clause in contract[section]:
                    verdict.clause_results.append(
                        ClauseResult(
                            clause_id=clause["clause_id"],
                            kind=clause["kind"],
                            surface=clause["surface"],
                            passed=True,
                        )
                    )
    if action == "add_to_cart":
        selected = product(session, args["product_id"])
        assert selected is not None
        if selected["stock"] < 0:
            fail(
                verdict,
                "post_cart_row",
                "db_delta",
                "postcondition",
                "negative stock",
                "stock >= 0",
            )


def apply_leak(session: FakeSession, verdict: Verdict, horizon: int) -> None:
    if session.leak is None or not any(n["method"] != "GET" for n in verdict.effect_diff.network):
        return
    leak, session.leak = session.leak, None
    if leak["delay_ms"] > horizon:
        return
    kind, t_ms = leak["kind"], 52 + leak["delay_ms"]
    if kind == "storage_write":
        entry = {"area": "local", "op": "set", "key": "__trk"}
        session.storage["local"]["__trk"] = "1"
        verdict.effect_diff.storage.append(entry)
        emit_event(session, verdict, "storage", entry, t_ms=t_ms, phase="post")
        fail(
            verdict,
            "inv_storage_untouched",
            "storage_untouched",
            "storage",
            "local:set:__trk",
            "no writes",
            surface="dom",
        )
        return
    third_party = kind == "third_party_fetch"
    path = "/api/cart" if kind == "background_poll" else "/api/analytics"
    network = {
        "method": "GET" if kind in ("background_poll", "third_party_fetch") else "POST",
        "url": "https://tracker.example.invalid/p" if third_party else urljoin(session.url, path),
        "approved": kind == "background_poll",
        "third_party": third_party,
        "phase": "post",
    }
    times = (
        range(t_ms, 53 + horizon, max(1, leak["delay_ms"])) if kind == "background_poll" else [t_ms]
    )
    for when in times:
        verdict.effect_diff.network.append(deepcopy(network))
        emit_event(
            session,
            verdict,
            "network_request",
            network_event(network, f"{verdict.run_id}.leak.{when}", 0),
            t_ms=when,
            phase="post",
        )
    if not network["approved"]:
        fail(
            verdict,
            "inv_no_third_party" if third_party else "inv_no_unapproved_endpoint",
            "no_third_party" if third_party else "no_unapproved_endpoint",
            "third_party" if third_party else "unapproved_endpoint",
            "GET tracker" if third_party else "POST /api/analytics",
            "no requests",
            surface="network",
        )
