from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable

import requests


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TERMS_MARKERS = (
    "terms and conditions",
    "accept the terms",
    "terms of use",
    "nutzungsbedingungen",
)


@dataclass(frozen=True)
class PublicationHttpError(RuntimeError):
    source: str
    kind: str
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        suffix = f" (HTTP {self.status_code})" if self.status_code is not None else ""
        return f"{self.source}:{self.kind}: {self.message}{suffix}"


class PublicationTermsRequired(PublicationHttpError):
    pass


class PublicationSchemaChanged(PublicationHttpError):
    pass


class PublicationRequestFailed(PublicationHttpError):
    pass


def _retry_after_seconds(response: requests.Response, fallback: float, maximum: float) -> float:
    value = str((getattr(response, "headers", {}) or {}).get("Retry-After") or "").strip()
    if value:
        try:
            return min(max(float(value), 0.0), maximum)
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                now = (
                    parsedate_to_datetime(response.headers.get("Date"))
                    if response.headers.get("Date")
                    else datetime.now(timezone.utc)
                )
                return min(max((target - now).total_seconds(), 0.0), maximum)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(max(fallback, 0.0), maximum)


class PublicationHttpClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        source: str,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        max_retry_after: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.source = source
        self.max_retries = max(0, max_retries)
        self.backoff_base = max(0.0, backoff_base)
        self.max_retry_after = max(0.0, max_retry_after)
        self.sleep = sleep

    @property
    def headers(self) -> dict[str, str]:
        contact = os.environ.get("CONTACT_EMAIL", "").strip()
        user_agent = "tutor-recommendation/2.0"
        if contact:
            user_agent += f" (+mailto:{contact})"
        return {"User-Agent": user_agent, "Accept": "application/json"}

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: tuple[float, float] = (10.0, 40.0),
        expected_keys: Iterable[str] = (),
    ) -> dict[str, Any]:
        response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout,
                    headers=self.headers,
                )
            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    self.sleep(min(self.backoff_base * (2**attempt), self.max_retry_after))
                    continue
                raise PublicationRequestFailed(
                    self.source,
                    "request_failed",
                    f"{type(exc).__name__}: {exc}",
                ) from exc

            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                delay = _retry_after_seconds(
                    response,
                    self.backoff_base * (2**attempt),
                    self.max_retry_after,
                )
                self.sleep(delay)
                continue
            text = str(getattr(response, "text", "") or "")
            content_type = str((getattr(response, "headers", {}) or {}).get("Content-Type") or "").lower()
            looks_html = "html" in content_type or text.lstrip().lower().startswith(("<!doctype html", "<html"))
            if looks_html and any(marker in text.lower() for marker in TERMS_MARKERS):
                raise PublicationTermsRequired(
                    self.source,
                    "terms_required",
                    "source requires manual acceptance of its terms",
                    status_code or None,
                )
            if status_code < 200 or status_code >= 300:
                raise PublicationRequestFailed(
                    self.source,
                    "request_failed",
                    "publication source returned a non-success response",
                    status_code or None,
                )
            break

        if response is None:
            raise PublicationRequestFailed(self.source, "request_failed", "no response")

        text = str(getattr(response, "text", "") or "")
        content_type = str((getattr(response, "headers", {}) or {}).get("Content-Type") or "").lower()
        looks_html = "html" in content_type or text.lstrip().lower().startswith(("<!doctype html", "<html"))
        if looks_html:
            lowered = text.lower()
            if any(marker in lowered for marker in TERMS_MARKERS):
                raise PublicationTermsRequired(
                    self.source,
                    "terms_required",
                    "source requires manual acceptance of its terms",
                    int(getattr(response, "status_code", 0) or 0) or None,
                )
            raise PublicationSchemaChanged(
                self.source,
                "schema_changed",
                "expected JSON but received HTML",
                int(getattr(response, "status_code", 0) or 0) or None,
            )

        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            raise PublicationSchemaChanged(
                self.source,
                "schema_changed",
                "response is not valid JSON",
                int(getattr(response, "status_code", 0) or 0) or None,
            ) from exc
        if not isinstance(data, dict):
            raise PublicationSchemaChanged(
                self.source,
                "schema_changed",
                "publication API returned a non-object response",
            )
        required = tuple(expected_keys)
        if required and not any(key in data for key in required):
            raise PublicationSchemaChanged(
                self.source,
                "schema_changed",
                f"response omitted expected keys: {', '.join(required)}",
            )
        return data
