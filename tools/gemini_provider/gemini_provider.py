#!/usr/bin/env python3
"""Gemini provider core used by Edit Aja Gemini.

This module intentionally has no third-party Python dependencies.  It provides
the provider-neutral pieces that can be mirrored by the native Qt/C++ adapter:
credential pooling, safe masking, project-aware cooldown behavior, and dynamic
Gemini model discovery.

API keys are never persisted by this module.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence


MAX_API_KEYS = 100
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT_SECONDS = 20.0
UNKNOWN_PROJECT_SCOPE = "__unknown_project__"


class GeminiProviderError(RuntimeError):
    """Base error for the Gemini provider helpers."""


class NoUsableCredential(GeminiProviderError):
    """Raised when every configured credential is unavailable."""


class GeminiHttpError(GeminiProviderError):
    """HTTP error returned by the Gemini API."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error_code: str = "",
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class GeminiCredential:
    """One Gemini API credential.

    project_id is optional, but strongly recommended when several keys are
    configured. Gemini rate limits are project-scoped, so keys belonging to the
    same project should share cooldown state after a 429 response.
    """

    api_key: str
    label: str = ""
    project_id: str = ""

    @property
    def quota_scope(self) -> str:
        return self.project_id.strip() or UNKNOWN_PROJECT_SCOPE

    @property
    def masked_key(self) -> str:
        return mask_api_key(self.api_key)


@dataclass
class _CredentialState:
    credential: GeminiCredential
    invalid: bool = False
    cooldown_until: float = 0.0
    failures: int = 0


def mask_api_key(api_key: str) -> str:
    """Return a log-safe representation of an API key."""

    value = api_key.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _normalize_credentials(
    credentials: Iterable[GeminiCredential],
) -> list[GeminiCredential]:
    result: list[GeminiCredential] = []
    seen: set[str] = set()

    for item in credentials:
        key = item.api_key.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(
            GeminiCredential(
                api_key=key,
                label=item.label.strip(),
                project_id=item.project_id.strip(),
            )
        )

    if not result:
        raise ValueError("At least one non-empty Gemini API key is required.")
    if len(result) > MAX_API_KEYS:
        raise ValueError(
            f"At most {MAX_API_KEYS} unique Gemini API keys are supported."
        )
    return result


class GeminiKeyPool:
    """In-memory pool for up to 100 Gemini credentials.

    The pool is round-robin for healthy credentials. A 429 response cools down
    every key in the same project quota scope. When project_id is unknown, all
    unknown-project keys share one conservative quota scope so the pool does not
    pretend that multiple keys automatically provide more quota.
    """

    def __init__(
        self,
        credentials: Iterable[GeminiCredential],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        normalized = _normalize_credentials(credentials)
        self._states = [_CredentialState(item) for item in normalized]
        self._clock = clock
        self._cursor = 0

    @classmethod
    def from_api_keys(
        cls,
        api_keys: Sequence[str],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "GeminiKeyPool":
        return cls(
            [GeminiCredential(api_key=value) for value in api_keys],
            clock=clock,
        )

    def __len__(self) -> int:
        return len(self._states)

    def _now(self, now: float | None) -> float:
        return self._clock() if now is None else float(now)

    def _find_state(self, api_key: str) -> _CredentialState:
        for state in self._states:
            if state.credential.api_key == api_key:
                return state
        raise KeyError("Gemini API key is not registered in this pool.")

    def acquire(self, *, now: float | None = None) -> GeminiCredential:
        """Return the next healthy credential without exposing the key in logs."""

        current = self._now(now)
        count = len(self._states)

        for offset in range(count):
            index = (self._cursor + offset) % count
            state = self._states[index]
            if state.invalid or state.cooldown_until > current:
                continue
            self._cursor = (index + 1) % count
            return state.credential

        raise NoUsableCredential("No Gemini API credential is currently usable.")

    def record_success(self, api_key: str) -> None:
        state = self._find_state(api_key)
        state.failures = 0
        state.cooldown_until = 0.0

    def record_failure(
        self,
        api_key: str,
        *,
        status_code: int,
        error_code: str = "",
        retry_after_seconds: float | None = None,
        now: float | None = None,
    ) -> None:
        """Update credential health after a failed request.

        - 401/403 invalidates only the failing credential.
        - 429 cools down the entire project quota scope.
        - transient 5xx errors cool down only the failing credential.
        - request-shape 4xx errors do not rotate credentials.
        """

        state = self._find_state(api_key)
        state.failures += 1
        current = self._now(now)

        if status_code in (401, 403):
            state.invalid = True
            return

        if status_code == 429:
            delay = max(1.0, float(retry_after_seconds or 60.0))
            scope = state.credential.quota_scope
            for candidate in self._states:
                if (
                    not candidate.invalid
                    and candidate.credential.quota_scope == scope
                ):
                    candidate.cooldown_until = max(
                        candidate.cooldown_until,
                        current + delay,
                    )
            return

        if status_code in (500, 502, 503, 504):
            default_delay = min(30.0, float(2 ** min(state.failures, 5)))
            delay = max(1.0, float(retry_after_seconds or default_delay))
            state.cooldown_until = max(state.cooldown_until, current + delay)

    def snapshot(self, *, now: float | None = None) -> list[dict[str, object]]:
        """Return status suitable for UI display without exposing secrets."""

        current = self._now(now)
        rows: list[dict[str, object]] = []
        for index, state in enumerate(self._states, start=1):
            if state.invalid:
                status = "invalid"
            elif state.cooldown_until > current:
                status = "cooldown"
            else:
                status = "ready"

            rows.append(
                {
                    "index": index,
                    "label": state.credential.label,
                    "project_id": state.credential.project_id,
                    "masked_key": state.credential.masked_key,
                    "status": status,
                    "cooldown_seconds": max(
                        0.0, round(state.cooldown_until - current, 3)
                    ),
                    "failures": state.failures,
                }
            )
        return rows


def parse_generate_models(payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Extract models that support generateContent from models.list payload."""

    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        return []

    result: list[dict[str, object]] = []
    for item in raw_models:
        if not isinstance(item, Mapping):
            continue

        methods = item.get("supportedGenerationMethods")
        if not isinstance(methods, list):
            methods = item.get("supportedActions")
        if not isinstance(methods, list) or "generateContent" not in methods:
            continue

        name = str(item.get("name", "")).strip()
        if not name:
            continue

        result.append(
            {
                "id": name.removeprefix("models/"),
                "name": name,
                "display_name": str(item.get("displayName", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "input_token_limit": item.get("inputTokenLimit"),
                "output_token_limit": item.get("outputTokenLimit"),
                "thinking": item.get("thinking"),
            }
        )

    return result


class GeminiRestClient:
    """Small REST client for model discovery.

    The API key is sent in the x-goog-api-key header, never in the URL.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener

    def _get_json(
        self,
        path: str,
        *,
        api_key: str,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        key = api_key.strip()
        if not key:
            raise ValueError("Gemini API key is empty.")

        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "x-goog-api-key": key,
            },
        )

        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            with response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            error_code = ""
            message = f"Gemini API HTTP {exc.code}"

            try:
                parsed = json.loads(body.decode("utf-8", errors="replace"))
                error = parsed.get("error", {})
                if isinstance(error, Mapping):
                    message = str(error.get("message") or message)
                    error_code = str(
                        error.get("status")
                        or error.get("code")
                        or ""
                    )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            try:
                retry_after_seconds = (
                    float(retry_after) if retry_after is not None else None
                )
            except ValueError:
                retry_after_seconds = None

            raise GeminiHttpError(
                exc.code,
                message,
                error_code=error_code,
                retry_after_seconds=retry_after_seconds,
            ) from exc
        except urllib.error.URLError as exc:
            raise GeminiProviderError(f"Gemini API network error: {exc.reason}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GeminiProviderError("Gemini API returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise GeminiProviderError("Gemini API returned an unexpected payload.")
        return payload

    def list_models(self, api_key: str) -> list[dict[str, object]]:
        """List all available models that support generateContent."""

        page_token = ""
        models: list[dict[str, object]] = []

        while True:
            query = {"pageSize": "1000"}
            if page_token:
                query["pageToken"] = page_token

            payload = self._get_json(
                "models",
                api_key=api_key,
                query=query,
            )
            models.extend(parse_generate_models(payload))

            next_token = str(payload.get("nextPageToken", "")).strip()
            if not next_token:
                break
            page_token = next_token

        return models


def _resolve_env_key() -> str:
    return (
        os.environ.get("GOOGLE_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
    )


def _cli_models() -> int:
    api_key = _resolve_env_key()
    if not api_key:
        raise SystemExit(
            "Set GOOGLE_API_KEY or GEMINI_API_KEY before running model discovery."
        )

    models = GeminiRestClient().list_models(api_key)
    print(json.dumps({"models": models}, indent=2, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "models",
        help="List models using GOOGLE_API_KEY or GEMINI_API_KEY.",
    )
    args = parser.parse_args(argv)

    if args.command == "models":
        return _cli_models()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
