import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
from gymnasium.utils.env_checker import check_env

from specx.safety.s1.baselines import run_random
from specx.safety.s1.env import SpecXFuzzEnv
from specx.safety.s1.mutations import MUTATIONS, mutate

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = json.loads((REPO_ROOT / "fixtures" / "tools" / "shop.tools.json").read_text())
CONTRACTS = json.loads((REPO_ROOT / "fixtures" / "contracts" / "shop.contracts.json").read_text())


class FakeSandbox:
    def __init__(self) -> None:
        self.run_number = 0
        self.counts = {"cart_items": 0, "orders": 0}

    def create_session(self, app: str, seed: int | None = None, leak=None) -> str:
        return f"session-{app}"

    def load_tools(self, session_id: str, tools: list[dict], contracts: list[dict]) -> None:
        self.tools = tools

    def reset(self, session_id: str, seed: int | None = None) -> None:
        self.run_number = 0
        self.counts = {"cart_items": 0, "orders": 0}

    def example_args(self, session_id: str, tool_id: str) -> dict[str, Any]:
        if tool_id.endswith("add_to_cart"):
            return {"product_id": 1, "qty": 1}
        if tool_id.endswith("place_order"):
            return {"confirm": True}
        return {}

    def invoke(
        self,
        session_id: str,
        tool_id: str,
        args: dict,
        *,
        source: str,
        post_observe_ms: int = 1500,
        screenshot: bool = False,
    ) -> dict[str, Any]:
        if any(isinstance(value, str) for value in args.values()):
            verdict = self._verdict(tool_id, status="error")
            verdict["violations"] = [
                {
                    "clause_id": "handler_type_error",
                    "severity": "high",
                    "signature": f"{tool_id}|handler_type_error|error|wrong type",
                }
            ]
            return verdict
        self.counts["cart_items"] += int(tool_id.endswith("add_to_cart"))
        return self._verdict(tool_id)

    def invoke_concurrent(
        self,
        session_id: str,
        calls: list[dict],
        *,
        source: str,
        post_observe_ms: int = 1500,
    ) -> dict[str, Any]:
        tool_id = calls[0]["tool_id"]
        if tool_id.endswith("place_order"):
            self.counts["orders"] += 2
            violation = {
                "clause_id": "inv_at_most_once",
                "severity": "high",
                "signature": "shop.place_order|inv_at_most_once|at_most_once|orders x2",
            }
            verdicts = [self._verdict(tool_id, status="fail", violation=violation) for _ in calls]
        else:
            verdicts = [self._verdict(tool_id) for _ in calls]
        return {"concurrency_group": "cg-test", "verdicts": verdicts}

    def replay(self, session_id: str, run_id: str) -> dict[str, Any]:
        return self._verdict("shop.list_products")

    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]:
        return {"db": {table: {"count": count, "rows": []} for table, count in self.counts.items()}}

    def close(self, session_id: str) -> None:
        return None

    def _verdict(
        self, tool_id: str, *, status: str = "pass", violation: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.run_number += 1
        clause_results = []
        violations = []
        if violation is not None:
            clause_results = [
                {
                    "clause_id": violation["clause_id"],
                    "kind": "at_most_once",
                    "surface": "db",
                    "passed": False,
                }
            ]
            violations = [copy.deepcopy(violation)]
        return {
            "run_id": f"run-{self.run_number}",
            "tool_id": tool_id,
            "status": status,
            "clause_results": clause_results,
            "violations": violations,
        }


def make_env(seed: int = 0) -> SpecXFuzzEnv:
    return SpecXFuzzEnv(
        FakeSandbox(),
        "shop",
        TOOLS,
        CONTRACTS,
        source="s1_random",
        horizon=25,
        seed=seed,
    )


def test_mutation_fallback_when_tool_has_no_integer_params() -> None:
    args, applied = mutate(TOOLS[0], {}, "boundary_max", np.random.default_rng(0))

    assert args == {}
    assert applied == "valid"


def test_error_not_rewarded() -> None:
    env = make_env()
    env.reset(seed=0)
    wrong_type_action = len(MUTATIONS) + MUTATIONS.index("wrong_type")

    _, reward, _, _, info = env.step(wrong_type_action)

    assert reward <= 0
    assert info["new_signatures"] == []
    env.close()


def test_environment_passes_gymnasium_checker() -> None:
    env = make_env()

    check_env(env, skip_render_check=True)

    env.close()


def test_random_baseline_finds_race_and_is_seeded() -> None:
    first = run_random(make_env(seed=11), 50, np.random.default_rng(11))
    second = run_random(make_env(seed=11), 50, np.random.default_rng(11))

    assert len(first.signatures) >= 1
    assert first == second
