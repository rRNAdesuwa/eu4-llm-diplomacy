"""Optional OpenAI-compatible planning adapter.

The adapter is intentionally opt-in and has no dependency beyond Python's
standard library.  It turns a snapshot into a model request, then validates
the returned JSON through :class:`bridge.compiler.ActionRequest` before the
caller can compile it.  It never writes credentials or responses to disk.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .compiler import ActionRequest, RequestError
from .protocol import Snapshot


class PlannerDisabledError(RuntimeError):
    """Raised when a planner is used without explicitly enabling it."""


class PlannerResponseError(ValueError):
    """Raised when an endpoint response is not one valid bridge action."""


class OpenAICompatiblePlanner:
    """Small adapter for ``/v1/chat/completions``-compatible endpoints.

    ``enabled`` defaults to ``False``.  An API key can be supplied directly
    for a process-local call or loaded from the named environment variable;
    the key is never persisted.  The planner only returns a validated
    ``ActionRequest`` and cannot execute a request itself.
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        api_key: str | None = None,
        api_key_env: str = "EU4LLM_API_KEY",
        enabled: bool = False,
        timeout: float = 20.0,
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must be an http:// or https:// URL")
        if not isinstance(model, str) or not model or len(model) > 128:
            raise ValueError("model must be a non-empty name no longer than 128 characters")
        if not isinstance(api_key_env, str) or not api_key_env.isidentifier():
            raise ValueError("api_key_env must be a valid environment variable name")
        if timeout <= 0 or timeout > 300:
            raise ValueError("timeout must be between 0 and 300 seconds")
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.enabled = enabled
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> "OpenAICompatiblePlanner":
        """Build a disabled-by-default planner from process environment only."""

        endpoint = os.environ.get("EU4LLM_OPENAI_ENDPOINT", "http://127.0.0.1:8000/v1/chat/completions")
        # A placeholder keeps construction side-effect-free when planning is
        # disabled and no endpoint configuration exists yet.
        model = os.environ.get("EU4LLM_OPENAI_MODEL", "disabled")
        enabled = os.environ.get("EU4LLM_ENABLE_PLANNER", "0") == "1"
        timeout_text = os.environ.get("EU4LLM_OPENAI_TIMEOUT", "20")
        try:
            timeout = float(timeout_text)
        except ValueError as error:
            raise ValueError("EU4LLM_OPENAI_TIMEOUT must be a number") from error
        return cls(endpoint, model, enabled=enabled, timeout=timeout)

    def _api_key(self) -> str | None:
        return self.api_key or os.environ.get(self.api_key_env)

    @staticmethod
    def _snapshot_payload(snapshot: Snapshot) -> dict[str, Any]:
        return {
            "id": snapshot.snapshot_id,
            "country": snapshot.country,
            "fields": dict(snapshot.fields),
        }

    def plan(self, snapshot: Snapshot) -> ActionRequest:
        """Ask the endpoint for one action and validate its JSON response."""

        if not self.enabled:
            raise PlannerDisabledError(
                "planner is disabled; set enabled=True or EU4LLM_ENABLE_PLANNER=1"
            )
        if not isinstance(snapshot, Snapshot):
            raise TypeError("snapshot must be a bridge.protocol.Snapshot")

        system_prompt = (
            "Return exactly one JSON object with keys id, action, and optional target. "
            "Allowed actions: snapshot, lock_diplomacy, unlock_diplomacy, "
            "improve_relations, declare_war. Targets are FRA for lock/unlock and ENG for "
            "improve_relations/declare_war. declare_war is fixed cb_core reconquest of "
            "Maine (177), requiring locked AI FRA, no truce/war/alliance and a valid "
            "ENG-owned FRA core and CB. The snapshot lacks these prerequisites: "
            "do not choose declare_war from this snapshot alone. "
            "Use no markdown and no additional keys."
        )
        user_payload = json.dumps(self._snapshot_payload(snapshot), ensure_ascii=False, separators=(",", ":"))
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        api_key = self._api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - endpoint is caller-configured
                raw_response = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise PlannerResponseError(f"planner request failed: {error}") from error

        try:
            decoded = json.loads(raw_response.decode("utf-8"))
            content = decoded["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message content is not text")
            # Be tolerant of a model adding a JSON code fence while still
            # requiring the actual payload to pass strict ActionRequest checks.
            if content.strip().startswith("```"):
                content = content.strip().split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return ActionRequest.from_json(content)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, RequestError) as error:
            raise PlannerResponseError(f"planner returned an invalid action: {error}") from error

