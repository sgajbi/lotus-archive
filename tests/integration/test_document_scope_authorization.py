from __future__ import annotations

from base64 import b64encode
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import (
    AccessEventType,
    AuthorizationDecision,
    InMemoryAccessAuditRepository,
)
from app.archive.models import (
    LIFECYCLE_TRANSITION_REASON_CODES,
    LegalHoldStatus,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
    PurgeStatus,
)
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.main import app
from tests.unit.test_archive_writer import valid_metadata_input


def _headers(
    *,
    caller_service: str = "lotus-report",
    tenant_id: str | None = "tenant-private-bank",
    region: str | None = "SG",
    trace_id: str = "trace-scope-test",
) -> dict[str, str]:
    headers = {
        "X-Correlation-Id": "corr-scope-test",
        "X-Trace-Id": trace_id,
        "X-Caller-Service": caller_service,
        "X-Actor-Type": "service",
        "X-Actor-Id": "scope-test-worker",
    }
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    if region is not None:
        headers["X-Region"] = region
    return headers


def _service(tmp_path: Path) -> ArchiveDocumentService:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
    )


def _create_document(
    client: TestClient,
    *,
    suffix: str = "owner",
    tenant_id: str = "tenant-private-bank",
    region: str = "SG",
    purge_eligible: bool = False,
) -> str:
    overrides: dict[str, object] = {
        "archive_request_id": f"archive-request-scope-{suffix}",
        "report_job_id": f"report-job-scope-{suffix}",
        "render_job_id": f"render-job-scope-{suffix}",
        "render_attempt_id": f"render-attempt-scope-{suffix}",
        "tenant_id": tenant_id,
        "region": region,
    }
    if purge_eligible:
        overrides.update(
            retention_start_date=date(2019, 1, 1),
            retain_until_date=date(2020, 1, 1),
        )
    metadata = valid_metadata_input(**overrides).model_dump(mode="json")
    response = client.post(
        "/documents",
        json={
            "metadata": metadata,
            "content_base64": b64encode(b"scope protected archive object").decode("ascii"),
        },
        headers=_headers(
            caller_service="lotus-render",
            tenant_id=tenant_id,
            region=region,
            trace_id=f"trace-create-{suffix}",
        ),
    )
    assert response.status_code == 201
    return str(response.json()["document_id"])


def _persist_legacy_transition(
    service: ArchiveDocumentService,
    *,
    source_document_id: str,
    target_document_id: str,
    suffix: str,
) -> None:
    transition_type = LifecycleTransitionType.SUPERSEDE
    service.repository.apply_lifecycle_transition(
        source_document_id=source_document_id,
        target_document_id=target_document_id,
        transition_type=transition_type,
        relationship=LifecycleRelationshipRecord(
            lifecycle_relationship_id=f"legacy-{suffix}",
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            transition_type=transition_type,
            transition_reason="Persisted before document-scope enforcement",
            transition_reason_code=LIFECYCLE_TRANSITION_REASON_CODES[transition_type],
            requested_by="legacy-migration",
        ),
    )


def test_access_events_refuse_foreign_tenant_before_returning_or_allow_audit(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            document_id = _create_document(client)
            response = client.get(
                f"/documents/{document_id}/access-events",
                headers=_headers(tenant_id="tenant-other", trace_id="trace-foreign-audit"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization_failed"
    events = service.audit_repository.list_by_document_id(document_id)
    matching = [event for event in events if event.trace_id == "trace-foreign-audit"]
    assert len(matching) == 1
    assert matching[0].authorization_decision is AuthorizationDecision.DENIED


@pytest.mark.parametrize(
    ("tenant_id", "region", "expected_status", "expected_code"),
    [
        ("tenant-other", "SG", 403, "authorization_failed"),
        ("tenant-private-bank", "EMEA", 403, "authorization_failed"),
        ("tenant-other", "EMEA", 403, "authorization_failed"),
        (None, "SG", 401, "caller_scope_missing"),
        ("tenant-private-bank", None, 401, "caller_scope_missing"),
    ],
)
@pytest.mark.parametrize(
    ("method", "path_suffix"),
    [
        ("GET", "access-events"),
        ("GET", "source-events"),
        ("GET", "retention"),
        ("POST", "purge-evaluation"),
    ],
)
def test_document_reads_require_each_persisted_scope_dimension(
    tmp_path: Path,
    tenant_id: str | None,
    region: str | None,
    expected_status: int,
    expected_code: str,
    method: str,
    path_suffix: str,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    trace_id = f"trace-denied-{method.lower()}-{path_suffix}-{tenant_id}-{region}"
    try:
        with TestClient(app) as client:
            document_id = _create_document(client)
            owner = client.request(
                method,
                f"/documents/{document_id}/{path_suffix}",
                headers=_headers(trace_id=f"trace-owner-{path_suffix}"),
            )
            response = client.request(
                method,
                f"/documents/{document_id}/{path_suffix}",
                headers=_headers(tenant_id=tenant_id, region=region, trace_id=trace_id),
            )
    finally:
        app.dependency_overrides.clear()

    assert owner.status_code == 200
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    matching = [
        event
        for event in service.audit_repository.list_by_document_id(document_id)
        if event.trace_id == trace_id
    ]
    assert len(matching) == 1
    assert matching[0].event_type is AccessEventType.AUTHORIZATION_DENIED
    assert matching[0].authorization_decision is AuthorizationDecision.DENIED


def test_foreign_mutations_preserve_holds_metadata_and_filesystem_object(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            document_id = _create_document(client, purge_eligible=True)
            metadata = service.repository.get_by_document_id(document_id)
            assert metadata is not None
            object_path = tmp_path / "objects" / metadata.storage_key
            assert object_path.is_file()

            denied_hold = client.post(
                f"/documents/{document_id}/legal-holds",
                json={"hold_reason": "Review", "authority_reference": "CASE-FOREIGN"},
                headers=_headers(tenant_id="tenant-other", trace_id="trace-foreign-hold"),
            )
            denied_purge = client.post(
                f"/documents/{document_id}/purge",
                headers=_headers(region="EMEA", trace_id="trace-foreign-purge"),
            )
            owner_hold = client.post(
                f"/documents/{document_id}/legal-holds",
                json={"hold_reason": "Review", "authority_reference": "CASE-OWNER"},
                headers=_headers(trace_id="trace-owner-hold"),
            )
            hold_id = owner_hold.json()["legal_hold_id"]
            denied_release = client.request(
                "DELETE",
                f"/documents/{document_id}/legal-holds/{hold_id}",
                json={"release_reason": "Foreign release"},
                headers=_headers(tenant_id="tenant-other", trace_id="trace-foreign-release"),
            )
    finally:
        app.dependency_overrides.clear()

    assert denied_hold.status_code == 403
    assert denied_purge.status_code == 403
    assert owner_hold.status_code == 201
    assert denied_release.status_code == 403
    holds = service.repository.list_legal_holds(document_id)
    assert len(holds) == 1
    assert holds[0].legal_hold_id == hold_id
    assert holds[0].hold_status is LegalHoldStatus.ACTIVE
    stored = service.repository.get_by_document_id(document_id)
    assert stored is not None
    assert stored.legal_hold_count == 1
    assert stored.purge_status is PurgeStatus.NOT_ELIGIBLE
    assert stored.purge_started_at is None
    assert object_path.is_file()
    denied_traces = {"trace-foreign-hold", "trace-foreign-purge", "trace-foreign-release"}
    denied_events = [
        event
        for event in service.audit_repository.list_by_document_id(document_id)
        if event.trace_id in denied_traces
    ]
    assert {event.trace_id for event in denied_events} == denied_traces
    assert all(
        event.authorization_decision is AuthorizationDecision.DENIED for event in denied_events
    )


def test_legacy_cross_scope_chain_is_refused_before_lineage_or_replay_can_leak_target(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix="legacy-source")
            target_id = _create_document(client, suffix="legacy-target")
            foreign_current_id = _create_document(
                client,
                suffix="legacy-foreign-current",
                tenant_id="tenant-other",
            )
            _persist_legacy_transition(
                service,
                source_document_id=source_id,
                target_document_id=target_id,
                suffix="source-target",
            )
            _persist_legacy_transition(
                service,
                source_document_id=target_id,
                target_document_id=foreign_current_id,
                suffix="target-foreign",
            )
            current = client.get(
                f"/documents/{source_id}/current",
                headers=_headers(trace_id="trace-legacy-current"),
            )
            source_events = client.get(
                f"/documents/{source_id}/source-events",
                headers=_headers(trace_id="trace-legacy-source-events"),
            )
            replay = client.post(
                f"/documents/{source_id}/supersede",
                json={
                    "target_document_id": target_id,
                    "transition_reason": "Retry legacy transition",
                },
                headers=_headers(trace_id="trace-legacy-replay"),
            )
    finally:
        app.dependency_overrides.clear()

    assert [current.status_code, source_events.status_code, replay.status_code] == [403] * 3
    assert all(
        foreign_current_id not in response.text for response in (current, source_events, replay)
    )
    assert len(service.repository.list_lifecycle_relationships(source_id)) == 1
    assert len(service.repository.list_lifecycle_relationships(target_id)) == 2
    source = service.repository.get_by_document_id(source_id)
    target = service.repository.get_by_document_id(target_id)
    assert source is not None and source.superseded_by_document_id == target_id
    assert target is not None and target.superseded_by_document_id == foreign_current_id
    traces = {"trace-legacy-current", "trace-legacy-source-events", "trace-legacy-replay"}
    events = [
        event
        for event in service.audit_repository.list_by_document_id(foreign_current_id)
        if event.trace_id in traces
    ]
    assert {event.trace_id for event in events} == traces
    assert all(event.event_type is AccessEventType.AUTHORIZATION_DENIED for event in events)
    assert all(event.authorization_decision is AuthorizationDecision.DENIED for event in events)


def test_same_scope_lifecycle_chain_current_lineage_and_replay_remain_unchanged(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix="same-scope-source")
            target_id = _create_document(client, suffix="same-scope-target")
            _persist_legacy_transition(
                service,
                source_document_id=source_id,
                target_document_id=target_id,
                suffix="same-scope",
            )
            current = client.get(
                f"/documents/{source_id}/current",
                headers=_headers(trace_id="trace-same-scope-current"),
            )
            source_events = client.get(
                f"/documents/{source_id}/source-events",
                headers=_headers(trace_id="trace-same-scope-source-events"),
            )
            replay = client.post(
                f"/documents/{source_id}/supersede",
                json={
                    "target_document_id": target_id,
                    "transition_reason": "Retry same-scope transition",
                },
                headers=_headers(trace_id="trace-same-scope-replay"),
            )
    finally:
        app.dependency_overrides.clear()

    assert current.status_code == 200
    assert current.json()["document_id"] == target_id
    assert source_events.status_code == 200
    assert source_events.json()["current_document_id"] == target_id
    assert replay.status_code == 201
    assert replay.json()["current_document_id"] == target_id
    assert len(service.repository.list_lifecycle_relationships(source_id)) == 1


@pytest.mark.parametrize("transition", ["supersede", "correct", "reissue"])
def test_lifecycle_authorizes_source_and_target_before_lookup_replay_or_write(
    tmp_path: Path,
    transition: str,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix=f"{transition}-source")
            target_id = _create_document(client, suffix=f"{transition}-target")
            foreign_target_id = _create_document(
                client,
                suffix=f"{transition}-foreign-target",
                tenant_id="tenant-other",
            )
            body = {
                "target_document_id": foreign_target_id,
                "transition_reason": "Approved document replacement",
            }
            denied_target = client.post(
                f"/documents/{source_id}/{transition}",
                json=body,
                headers=_headers(trace_id=f"trace-{transition}-foreign-target"),
            )
            denied_source = client.post(
                f"/documents/{source_id}/{transition}",
                json={**body, "target_document_id": target_id},
                headers=_headers(
                    tenant_id="tenant-other",
                    trace_id=f"trace-{transition}-foreign-source",
                ),
            )
            missing_scope = client.post(
                f"/documents/{source_id}/{transition}",
                json={**body, "target_document_id": target_id},
                headers=_headers(tenant_id=None, trace_id=f"trace-{transition}-missing"),
            )
            allowed = client.post(
                f"/documents/{source_id}/{transition}",
                json={**body, "target_document_id": target_id},
                headers=_headers(trace_id=f"trace-{transition}-owner"),
            )
            denied_replay = client.post(
                f"/documents/{source_id}/{transition}",
                json={**body, "target_document_id": target_id},
                headers=_headers(
                    region="EMEA",
                    trace_id=f"trace-{transition}-foreign-replay",
                ),
            )
            owner_replay = client.post(
                f"/documents/{source_id}/{transition}",
                json={**body, "target_document_id": target_id},
                headers=_headers(trace_id=f"trace-{transition}-owner-replay"),
            )
    finally:
        app.dependency_overrides.clear()

    assert denied_target.status_code == 403
    assert denied_source.status_code == 403
    assert missing_scope.status_code == 401
    assert allowed.status_code == 201
    assert denied_replay.status_code == 403
    assert owner_replay.status_code == 201
    assert (
        owner_replay.json()["lifecycle_relationship_id"]
        == allowed.json()["lifecycle_relationship_id"]
    )
    relationships = service.repository.list_lifecycle_relationships(source_id)
    assert len(relationships) == 1
    source = service.repository.get_by_document_id(source_id)
    target = service.repository.get_by_document_id(target_id)
    foreign_target = service.repository.get_by_document_id(foreign_target_id)
    assert source is not None and source.superseded_by_document_id == target_id
    assert target is not None
    assert foreign_target is not None
    assert foreign_target.superseded_by_document_id is None
    assert foreign_target.supersedes_document_id is None
    assert foreign_target.correction_of_document_id is None
    assert foreign_target.reissue_of_document_id is None
