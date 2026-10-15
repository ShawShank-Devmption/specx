"""Gymnasium environment that fuzzes the published sandbox API."""

import hashlib
from typing import Any, Protocol

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from specx.safety.s1.mutations import MUTATIONS, mutate

STATUSES = ["pass", "fail", "error", "unverifiable"]


class SandboxClientLike(Protocol):
    def create_session(
        self, app: str, seed: int | None = None, leak: dict[str, Any] | None = None
    ) -> str: ...

    def load_tools(
        self,
        session_id: str,
        tools: list[dict[str, Any]],
        contracts: list[dict[str, Any]],
    ) -> None: ...

    def reset(self, session_id: str, seed: int | None = None) -> None: ...

    def invoke(
        self,
        session_id: str,
        tool_id: str,
        args: dict[str, Any],
        *,
        source: str,
        post_observe_ms: int = 1500,
        screenshot: bool = False,
    ) -> dict[str, Any]: ...

    def invoke_concurrent(
        self,
        session_id: str,
        calls: list[dict[str, Any]],
        *,
        source: str,
        post_observe_ms: int = 1500,
    ) -> dict[str, Any]: ...

    def replay(self, session_id: str, run_id: str) -> dict[str, Any]: ...

    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]: ...

    def example_args(self, session_id: str, tool_id: str) -> dict[str, Any]: ...

    def close(self, session_id: str) -> None: ...


class SpecXFuzzEnv(gym.Env[np.ndarray, int]):
    """Discrete tool/mutation actions with contract-violation novelty rewards."""

    metadata: dict[str, Any] = {"render_modes": []}  # noqa: RUF012

    def __init__(
        self,
        client: SandboxClientLike,
        app: str,
        tools: list[dict[str, Any]],
        contracts: list[dict[str, Any]],
        *,
        source: str,
        horizon: int = 25,
        post_observe_ms: int = 300,
        seed: int = 0,
    ):
        super().__init__()
        if not tools:
            raise ValueError("at least one tool is required")
        if horizon <= 0:
            raise ValueError("horizon must be positive")
        self.client = client
        self.app = app
        self.tools = tools
        self.contracts = contracts
        self.source = source
        self.horizon = horizon
        self.post_observe_ms = post_observe_ms
        self.seed_value = seed
        self.session_id = client.create_session(app, seed=seed)
        client.load_tools(self.session_id, tools, contracts)

        self.n_actions = len(tools) * len(MUTATIONS)
        self.action_space = spaces.Discrete(self.n_actions)  # type: ignore[assignment]
        observation_size = len(tools) + len(STATUSES) + 32 + 6 + 1
        self.observation_space = spaces.Box(
            low=0.0,
            high=np.finfo(np.float32).max,
            shape=(observation_size,),
            dtype=np.float32,
        )
        self._all_signatures: set[str] = set()
        self._episode_signatures: set[str] = set()
        self._seen_states: set[tuple[int, ...]] = set()
        self._db_tables: list[str] = []
        self._last_tool: int | None = None
        self._last_status: str | None = None
        self._last_run_id: str | None = None
        self._step = 0

    @property
    def all_signatures(self) -> set[str]:
        return set(self._all_signatures)

    def _db_counts(self) -> tuple[int, ...]:
        state = self.client.state(self.session_id)
        db = state.get("db", {})
        if not self._db_tables:
            self._db_tables = sorted(db)[:6]
        counts = [int(db.get(table, {}).get("count", 0)) for table in self._db_tables]
        return tuple((counts + [0] * 6)[:6])

    def _observation(self, counts: tuple[int, ...] | None = None) -> np.ndarray:
        last_tool = np.zeros(len(self.tools), dtype=np.float32)
        if self._last_tool is not None:
            last_tool[self._last_tool] = 1.0
        last_status = np.zeros(len(STATUSES), dtype=np.float32)
        if self._last_status in STATUSES:
            last_status[STATUSES.index(self._last_status)] = 1.0
        bitmap = np.zeros(32, dtype=np.float32)
        for signature in self._episode_signatures:
            digest = hashlib.sha256(signature.encode()).digest()
            bitmap[int.from_bytes(digest[:4], "big") % 32] = 1.0
        raw_counts = counts if counts is not None else self._db_counts()
        db_counts = np.log1p(np.asarray(raw_counts, dtype=np.float32))
        progress = np.asarray([self._step / self.horizon], dtype=np.float32)
        return np.concatenate((last_tool, last_status, bitmap, db_counts, progress)).astype(
            np.float32
        )

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        reset_seed = self.seed_value if seed is None else seed
        self.client.reset(self.session_id, seed=reset_seed)
        self._episode_signatures.clear()
        self._last_tool = None
        self._last_status = None
        self._last_run_id = None
        self._step = 0
        counts = self._db_counts()
        self._seen_states = {counts}
        return self._observation(counts), {}

    def _invoke(self, tool_index: int, requested_mutation: str) -> tuple[list[dict[str, Any]], str]:
        tool = self.tools[tool_index]
        tool_id = str(tool["tool_id"])
        valid_args = self.client.example_args(self.session_id, tool_id)
        args, applied = mutate(tool, valid_args, requested_mutation, self.np_random)
        if applied == "replay_last" and self._last_run_id is not None:
            return [self.client.replay(self.session_id, self._last_run_id)], applied
        if applied == "replay_last":
            applied = "valid"
        if applied == "concurrent_x2":
            result = self.client.invoke_concurrent(
                self.session_id,
                [{"tool_id": tool_id, "args": args}, {"tool_id": tool_id, "args": args}],
                source=self.source,
                post_observe_ms=self.post_observe_ms,
            )
            return list(result["verdicts"]), applied
        verdict = self.client.invoke(
            self.session_id,
            tool_id,
            args,
            source=self.source,
            post_observe_ms=self.post_observe_ms,
        )
        return [verdict], applied

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if not self.action_space.contains(action):
            raise ValueError(f"action {action} is outside the action space")
        tool_index, mutation_index = divmod(int(action), len(MUTATIONS))
        verdicts, applied = self._invoke(tool_index, MUTATIONS[mutation_index])
        self._step += 1
        self._last_tool = tool_index
        self._last_status = str(verdicts[-1].get("status", "error"))
        self._last_run_id = verdicts[-1].get("run_id")

        failed_clause_ids = {
            result.get("clause_id")
            for verdict in verdicts
            for result in verdict.get("clause_results", [])
            if result.get("passed") is False
        }
        error_without_failed_clause = (
            all(verdict.get("status") == "error" for verdict in verdicts) and not failed_clause_ids
        )
        signatures = {
            violation["signature"]
            for verdict in verdicts
            for violation in verdict.get("violations", [])
            if violation.get("clause_id") in failed_clause_ids and violation.get("signature")
        }
        new_episode = sorted(signatures - self._episode_signatures)
        new_run = signatures - self._all_signatures
        counts = self._db_counts()

        reward = -0.02
        if not error_without_failed_clause:
            reward += len(new_episode) + 0.5 * len(new_run)
            if counts not in self._seen_states:
                reward += 0.1
        self._episode_signatures.update(signatures)
        self._all_signatures.update(signatures)
        self._seen_states.add(counts)

        terminated = self._step >= self.horizon
        info = {"verdicts": verdicts, "new_signatures": new_episode, "mutation": applied}
        return self._observation(counts), reward, terminated, False, info

    def close(self) -> None:
        self.client.close(self.session_id)
