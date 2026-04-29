from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

from prometheus_client import Counter, Histogram

METRIC_OPERATION_LABEL = "operation"
METRIC_STATUS_LABEL = "status"
METRIC_FAILURE_CATEGORY_LABEL = "failure_category"
METRIC_STATE_LABEL = "state"
METRIC_REASON_LABEL = "reason"
METRIC_FRESHNESS_BUCKET_LABEL = "freshness_bucket"

ARCHIVE_METRIC_LABELS = frozenset(
    {
        METRIC_FRESHNESS_BUCKET_LABEL,
        METRIC_OPERATION_LABEL,
        METRIC_REASON_LABEL,
        METRIC_STATE_LABEL,
        METRIC_STATUS_LABEL,
        METRIC_FAILURE_CATEGORY_LABEL,
    }
)
FORBIDDEN_METRIC_LABELS = frozenset(
    {
        "account_id",
        "archive_request_id",
        "booking_center_code",
        "bucket",
        "client_id",
        "client_name",
        "correlation_id",
        "document_id",
        "idempotency_key",
        "legal_hold_id",
        "lifecycle_relationship_id",
        "portfolio_id",
        "portfolio_name",
        "raw_document_content",
        "raw_upstream_payload",
        "render_job_id",
        "report_job_id",
        "request_id",
        "snapshot_id",
        "storage_key",
        "tenant_id",
        "trace_id",
    }
)

IMPLEMENTED_ARCHIVE_OPERATIONS = frozenset(
    {
        "access_events_lookup",
        "archive_create",
        "binary_download",
        "current_document_lookup",
        "legal_hold_release",
        "legal_hold_set",
        "lifecycle_correct",
        "lifecycle_reissue",
        "lifecycle_supersede",
        "metadata_lookup",
        "purge_evaluation",
        "purge_execution",
        "retention_lookup",
    }
)
ARCHIVE_OPERATION_STATUSES = frozenset(
    {
        "active",
        "archived",
        "clear",
        "eligible",
        "failed",
        "not_eligible",
        "purged",
        "succeeded",
    }
)
ARCHIVE_SUPPORTABILITY_STATES = frozenset({"ready", "degraded", "unavailable"})
ARCHIVE_SUPPORTABILITY_REASONS = frozenset(
    {
        "archive_supportability_ready",
        "archive_supportability_draining",
        "archive_capability_unavailable",
    }
)
ARCHIVE_SUPPORTABILITY_FRESHNESS_BUCKETS = frozenset({"current", "unknown"})

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class ArchiveMetricContract:
    name: str
    metric_type: str
    labels: tuple[str, ...]
    implemented: bool
    description: str


ARCHIVE_METRIC_CONTRACTS: tuple[ArchiveMetricContract, ...] = (
    ArchiveMetricContract(
        name="lotus_archive_operations_total",
        metric_type="counter",
        labels=(METRIC_OPERATION_LABEL, METRIC_STATUS_LABEL, METRIC_FAILURE_CATEGORY_LABEL),
        implemented=True,
        description=(
            "Counts supported archive create, retrieval, retention, purge, legal-hold, and "
            "lifecycle operations by bounded operation, status, and failure category."
        ),
    ),
    ArchiveMetricContract(
        name="lotus_archive_operation_duration_seconds",
        metric_type="histogram",
        labels=(METRIC_OPERATION_LABEL, METRIC_STATUS_LABEL, METRIC_FAILURE_CATEGORY_LABEL),
        implemented=True,
        description="Measures supported archive operation duration using bounded labels only.",
    ),
    ArchiveMetricContract(
        name="lotus_archive_document_size_bytes",
        metric_type="histogram",
        labels=(METRIC_STATUS_LABEL,),
        implemented=True,
        description=(
            "Measures archived or downloaded generated-document size without document, report, "
            "render, portfolio, tenant, trace, correlation, or storage identifiers."
        ),
    ),
    ArchiveMetricContract(
        name="lotus_archive_supportability_total",
        metric_type="counter",
        labels=(METRIC_STATE_LABEL, METRIC_REASON_LABEL, METRIC_FRESHNESS_BUCKET_LABEL),
        implemented=True,
        description=(
            "Counts source-backed RFC-0108 archive supportability observations using bounded "
            "state, reason, and freshness labels."
        ),
    ),
)

_ARCHIVE_OPERATIONS_TOTAL = Counter(
    "lotus_archive_operations_total",
    ARCHIVE_METRIC_CONTRACTS[0].description,
    [METRIC_OPERATION_LABEL, METRIC_STATUS_LABEL, METRIC_FAILURE_CATEGORY_LABEL],
)
_ARCHIVE_OPERATION_DURATION_SECONDS = Histogram(
    "lotus_archive_operation_duration_seconds",
    ARCHIVE_METRIC_CONTRACTS[1].description,
    [METRIC_OPERATION_LABEL, METRIC_STATUS_LABEL, METRIC_FAILURE_CATEGORY_LABEL],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
_ARCHIVE_DOCUMENT_SIZE_BYTES = Histogram(
    "lotus_archive_document_size_bytes",
    ARCHIVE_METRIC_CONTRACTS[2].description,
    [METRIC_STATUS_LABEL],
    buckets=(1_024, 10_240, 102_400, 1_048_576, 5_242_880, 10_485_760),
)
_ARCHIVE_SUPPORTABILITY_TOTAL = Counter(
    "lotus_archive_supportability_total",
    ARCHIVE_METRIC_CONTRACTS[3].description,
    [METRIC_STATE_LABEL, METRIC_REASON_LABEL, METRIC_FRESHNESS_BUCKET_LABEL],
)


def validate_archive_metric_contracts() -> None:
    names = [contract.name for contract in ARCHIVE_METRIC_CONTRACTS]
    if len(names) != len(set(names)):
        raise ValueError("duplicate_archive_metric_name")
    for contract in ARCHIVE_METRIC_CONTRACTS:
        _validate_labels(contract.labels)


def record_archive_operation(
    *,
    operation: str,
    status: str,
    failure_category: str | None = None,
    duration_seconds: float | None = None,
) -> None:
    operation_label = _implemented_operation(operation)
    status_label = _bounded_status(status)
    failure_label = _bounded_failure_category(failure_category)
    _ARCHIVE_OPERATIONS_TOTAL.labels(
        operation=operation_label,
        status=status_label,
        failure_category=failure_label,
    ).inc()
    if duration_seconds is not None:
        _ARCHIVE_OPERATION_DURATION_SECONDS.labels(
            operation=operation_label,
            status=status_label,
            failure_category=failure_label,
        ).observe(max(0.0, duration_seconds))


def record_archive_document_size(*, status: str, size_bytes: int | None) -> None:
    if size_bytes is None:
        return
    _ARCHIVE_DOCUMENT_SIZE_BYTES.labels(status=_bounded_status(status)).observe(max(0, size_bytes))


def record_archive_supportability(
    *,
    state: str,
    reason: str,
    freshness_bucket: str,
) -> None:
    _ARCHIVE_SUPPORTABILITY_TOTAL.labels(
        state=_bounded_supportability_state(state),
        reason=_bounded_supportability_reason(reason),
        freshness_bucket=_bounded_supportability_freshness_bucket(freshness_bucket),
    ).inc()


def archive_metric(operation: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started_at = perf_counter()
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                record_archive_operation(
                    operation=operation,
                    status="failed",
                    failure_category=_failure_category_from_exception(exc),
                    duration_seconds=perf_counter() - started_at,
                )
                raise
            status = _status_from_result(operation, result)
            record_archive_operation(
                operation=operation,
                status=status,
                duration_seconds=perf_counter() - started_at,
            )
            record_archive_document_size(
                status=status,
                size_bytes=_document_size_from_result(result),
            )
            return result

        return wrapper

    return decorator


def _status_from_result(operation: str, result: object) -> str:
    if operation == "retention_lookup":
        if hasattr(result, "legal_hold_status"):
            return str(getattr(result, "legal_hold_status"))
        return "clear"
    if operation in {"legal_hold_set", "legal_hold_release"} and hasattr(result, "hold_status"):
        return str(getattr(result, "hold_status"))
    if hasattr(result, "size_bytes") and hasattr(result, "document_id"):
        return "archived"
    if hasattr(result, "hold_status"):
        return str(getattr(result, "hold_status"))
    if isinstance(result, tuple) and len(result) >= 2:
        reason_code = str(result[1])
        if reason_code in {"purged", "already_purged"}:
            return "purged"
        if reason_code in {"retention_elapsed", "eligible"}:
            return "eligible"
        if reason_code in {
            "legal_hold_active",
            "retain_until_date_missing",
            "retention_period_active",
            "not_eligible",
        }:
            return "not_eligible"
    return "succeeded"


def _document_size_from_result(result: object) -> int | None:
    if hasattr(result, "size_bytes"):
        return int(getattr(result, "size_bytes"))
    if isinstance(result, tuple):
        for item in result:
            if isinstance(item, bytes):
                return len(item)
            if hasattr(item, "size_bytes"):
                return int(getattr(item, "size_bytes"))
    return None


def _failure_category_from_exception(exc: Exception) -> str:
    name = exc.__class__.__name__
    if name.endswith("Error"):
        name = name[:-5]
    normalized = []
    for index, character in enumerate(name):
        if character.isupper() and index:
            normalized.append("_")
        normalized.append(character.lower())
    return "".join(normalized) or "archive_operation_failed"


def _validate_labels(labels: Iterable[str]) -> None:
    label_set = set(labels)
    forbidden = label_set & FORBIDDEN_METRIC_LABELS
    if forbidden:
        raise ValueError(f"forbidden_archive_metric_label:{sorted(forbidden)[0]}")
    unsupported = label_set - ARCHIVE_METRIC_LABELS
    if unsupported:
        raise ValueError(f"unsupported_archive_metric_label:{sorted(unsupported)[0]}")


def _implemented_operation(operation: str) -> str:
    if operation not in IMPLEMENTED_ARCHIVE_OPERATIONS:
        raise ValueError(f"unsupported_archive_metric_operation:{operation}")
    return operation


def _bounded_status(status: str) -> str:
    if status in ARCHIVE_OPERATION_STATUSES:
        return status
    return "failed"


def _bounded_failure_category(failure_category: str | None) -> str:
    if not failure_category:
        return "none"
    normalized = failure_category.strip().lower().replace("-", "_")
    if not normalized:
        return "none"
    if len(normalized) > 80:
        return "other"
    if not all(character.isalnum() or character == "_" for character in normalized):
        return "other"
    return normalized


def _bounded_supportability_state(state: str) -> str:
    if state in ARCHIVE_SUPPORTABILITY_STATES:
        return state
    return "unavailable"


def _bounded_supportability_reason(reason: str) -> str:
    if reason in ARCHIVE_SUPPORTABILITY_REASONS:
        return reason
    return "archive_capability_unavailable"


def _bounded_supportability_freshness_bucket(freshness_bucket: str) -> str:
    if freshness_bucket in ARCHIVE_SUPPORTABILITY_FRESHNESS_BUCKETS:
        return freshness_bucket
    return "unknown"
