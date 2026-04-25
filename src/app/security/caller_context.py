from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


CALLER_SERVICE_HEADER = "x-caller-service"
ACTOR_TYPE_HEADER = "x-actor-type"
ACTOR_ID_HEADER = "x-actor-id"


class CallerContextMissingError(ValueError):
    def __init__(self, missing_headers: tuple[str, ...]) -> None:
        self.missing_headers = missing_headers
        super().__init__(f"Missing caller context headers: {', '.join(missing_headers)}")


@dataclass(frozen=True)
class CallerContext:
    caller_service: str
    actor_type: str
    actor_id: str
    correlation_id: str


def caller_context_from_headers(
    headers: Mapping[str, str],
    *,
    correlation_id: str,
) -> CallerContext:
    normalized = {key.lower(): value.strip() for key, value in headers.items()}
    missing = tuple(
        header
        for header in (CALLER_SERVICE_HEADER, ACTOR_TYPE_HEADER, ACTOR_ID_HEADER)
        if not normalized.get(header)
    )
    if missing:
        raise CallerContextMissingError(missing)

    return CallerContext(
        caller_service=normalized[CALLER_SERVICE_HEADER],
        actor_type=normalized[ACTOR_TYPE_HEADER],
        actor_id=normalized[ACTOR_ID_HEADER],
        correlation_id=correlation_id,
    )
