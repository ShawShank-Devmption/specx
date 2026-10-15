"""Synchronous client for sandbox HTTP API v1, shared by Developers B and C.

API versions are read from the platform header; legacy body metadata remains accepted.
"""

import os
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from specx.client.schemas import validate


class SandboxError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class SandboxClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (
            base_url or os.environ.get("SPECX_SANDBOX_URL", "http://127.0.0.1:4000")
        ).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=60)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """Release HTTP resources; close(session_id) separately destroys a remote session."""
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.RequestError as error:
            raise SandboxError("transport_error", str(error)) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise SandboxError(
                "invalid_response", f"HTTP {response.status_code}: expected JSON"
            ) from error
        if not isinstance(payload, dict):
            raise SandboxError("invalid_response", "Expected a JSON object")
        if "error" in payload:
            error_body = payload["error"]
            if not isinstance(error_body, dict):
                raise SandboxError("invalid_response", "Malformed sandbox error envelope")
            raise SandboxError(
                str(error_body.get("code", "sandbox_error")),
                str(error_body.get("message", "Unspecified sandbox error")),
            )
        if not response.is_success:
            raise SandboxError(f"http_{response.status_code}", response.reason_phrase)
        header_version = response.headers.get("x-specx-api-version", "1")
        if header_version != "1":
            raise SandboxError(
                "api_version", f"Unsupported sandbox API version: {header_version!r}"
            )
        version = payload.pop("api_version", "1")
        if version != "1":
            raise SandboxError("api_version", f"Unsupported sandbox API version: {version!r}")
        return payload

    @staticmethod
    def _path(session_id: str, suffix: str = "") -> str:
        return f"/sessions/{quote(session_id, safe='')}{suffix}"

    @staticmethod
    def _verdict(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise SandboxError("invalid_response", "Expected a verdict object")
        if payload.get("api_version", "1") != "1":
            raise SandboxError("api_version", "Unsupported verdict API version")
        record = {key: value for key, value in payload.items() if key != "api_version"}
        validate("verdict", record)
        return record

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_session(
        self, app: str, seed: int | None = None, leak: dict[str, Any] | None = None
    ) -> str:
        body: dict[str, Any] = {"app": app}
        if seed is not None:
            body["seed"] = seed
        if leak is not None:
            body["leak"] = leak
        payload = self._request("POST", "/sessions", json=body)
        session_id = payload.get("session_id")
        if not isinstance(session_id, str):
            raise SandboxError("invalid_response", "Missing session_id")
        return session_id

    def load_tools(
        self, session_id: str, tools: list[dict[str, Any]], contracts: list[dict[str, Any]]
    ) -> None:
        for tool in tools:
            validate("tool_definition", tool)
        for contract in contracts:
            validate("contract", contract)
        self._request(
            "PUT", self._path(session_id, "/tools"), json={"tools": tools, "contracts": contracts}
        )

    def reset(self, session_id: str, seed: int | None = None) -> None:
        self._request(
            "POST", self._path(session_id, "/reset"), json={} if seed is None else {"seed": seed}
        )

    def invoke(
        self,
        session_id: str,
        tool_id: str,
        args: dict[str, Any],
        *,
        source: str,
        post_observe_ms: int = 1500,
        screenshot: bool = False,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            self._path(session_id, "/invoke"),
            json={
                "tool_id": tool_id,
                "args": args,
                "source": source,
                "post_observe_ms": post_observe_ms,
                "screenshot": screenshot,
            },
        )
        return self._verdict(payload)

    def invoke_concurrent(
        self,
        session_id: str,
        calls: list[dict[str, Any]],
        *,
        source: str,
        post_observe_ms: int = 1500,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            self._path(session_id, "/invoke_concurrent"),
            json={"calls": calls, "source": source, "post_observe_ms": post_observe_ms},
        )
        if not isinstance(payload.get("verdicts"), list):
            raise SandboxError("invalid_response", "Missing verdicts")
        payload["verdicts"] = [self._verdict(verdict) for verdict in payload["verdicts"]]
        return payload

    def replay(self, session_id: str, run_id: str) -> dict[str, Any]:
        return self._verdict(
            self._request("POST", self._path(session_id, "/replay"), json={"run_id": run_id})
        )

    def events(self, session_id: str, since_seq: int = 0) -> list[dict[str, Any]]:
        records = self._request(
            "GET", self._path(session_id, "/events"), params={"since_seq": since_seq}
        ).get("events")
        if not isinstance(records, list):
            raise SandboxError("invalid_response", "Missing events")
        for record in records:
            validate("event_record", record)
        return records

    def state(self, session_id: str, screenshot: bool = False) -> dict[str, Any]:
        return self._request(
            "GET", self._path(session_id, "/state"), params={"screenshot": str(screenshot).lower()}
        )

    def example_args(self, session_id: str, tool_id: str) -> dict[str, Any]:
        args = self._request(
            "GET", self._path(session_id, "/example_args"), params={"tool_id": tool_id}
        ).get("args")
        if not isinstance(args, dict):
            raise SandboxError("invalid_response", "Missing args")
        return args

    def apply(self, session_id: str, state: dict[str, Any]) -> None:
        self._request("POST", self._path(session_id, "/apply"), json={"state": state})

    def dom_action(
        self,
        session_id: str,
        action: str,
        *,
        ref: str | None = None,
        text: str | None = None,
        url: str | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        body = {
            name: value
            for name, value in {
                "action": action,
                "ref": ref,
                "text": text,
                "url": url,
                "key": key,
            }.items()
            if value is not None
        }
        return self._request("POST", self._path(session_id, "/dom_action"), json=body)

    def inject_leak(self, session_id: str, kind: str, delay_ms: int) -> None:
        self._request(
            "POST",
            self._path(session_id, "/inject_leak"),
            json={"kind": kind, "delay_ms": delay_ms},
        )

    def close(self, session_id: str) -> None:
        self._request("DELETE", self._path(session_id))
