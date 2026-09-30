from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.archive.api import archive_service
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import AuthorizationDecision
from app.archive.postgres_repository import (
    PostgresAccessAuditRepository,
    PostgresArchiveDocumentRepository,
)
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.main import app
from tests.database_proof import required_database_url
from tests.integration.test_document_scope_authorization import (
    _create_document,
    _headers,
    _persist_legacy_transition,
)

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute("TRUNCATE archive_access_audit")
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )


def _postgres_service(tmp_path: Path) -> ArchiveDocumentService:
    repository = PostgresArchiveDocumentRepository(DATABASE_URL)
    storage = FilesystemObjectStorage(tmp_path / "objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=PostgresAccessAuditRepository(DATABASE_URL),
    )


@pytest.mark.parametrize(
    ("tenant_id", "region", "scope_name"),
    [
        ("tenant-other", "SG", "tenant"),
        ("tenant-private-bank", "EMEA", "region"),
    ],
)
def test_postgres_http_denials_write_no_hold_or_purge_and_retain_object(
    tmp_path: Path,
    tenant_id: str,
    region: str,
    scope_name: str,
) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            held_id = _create_document(client, suffix=f"pg-{scope_name}-held")
            purge_id = _create_document(
                client,
                suffix=f"pg-{scope_name}-purge",
                purge_eligible=True,
            )
            purge_metadata = service.repository.get_by_document_id(purge_id)
            assert purge_metadata is not None
            object_path = tmp_path / "objects" / purge_metadata.storage_key
            assert object_path.is_file()

            access = client.get(
                f"/documents/{held_id}/access-events",
                headers=_headers(
                    tenant_id=tenant_id,
                    region=region,
                    trace_id=f"trace-pg-{scope_name}-access",
                ),
            )
            source_events = client.get(
                f"/documents/{held_id}/source-events",
                headers=_headers(
                    tenant_id=tenant_id,
                    region=region,
                    trace_id=f"trace-pg-{scope_name}-source-events",
                ),
            )
            hold = client.post(
                f"/documents/{held_id}/legal-holds",
                json={"hold_reason": "Review", "authority_reference": "CASE-FOREIGN"},
                headers=_headers(
                    tenant_id=tenant_id,
                    region=region,
                    trace_id=f"trace-pg-{scope_name}-hold",
                ),
            )
            owner_hold = client.post(
                f"/documents/{held_id}/legal-holds",
                json={"hold_reason": "Review", "authority_reference": "CASE-OWNER"},
                headers=_headers(trace_id=f"trace-pg-{scope_name}-owner-hold"),
            )
            release = client.request(
                "DELETE",
                f"/documents/{held_id}/legal-holds/{owner_hold.json()['legal_hold_id']}",
                json={"release_reason": "Foreign release"},
                headers=_headers(
                    tenant_id=tenant_id,
                    region=region,
                    trace_id=f"trace-pg-{scope_name}-release",
                ),
            )
            purge = client.post(
                f"/documents/{purge_id}/purge",
                headers=_headers(
                    tenant_id=tenant_id,
                    region=region,
                    trace_id=f"trace-pg-{scope_name}-purge",
                ),
            )
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in (access, source_events, hold, release, purge)] == [
        403
    ] * 5
    with psycopg.connect(DATABASE_URL) as connection:
        foreign_holds = connection.execute(
            "SELECT count(*) FROM archive_legal_holds "
            "WHERE document_id = %s AND authority_reference = 'CASE-FOREIGN'",
            (held_id,),
        ).fetchone()
        owner_hold_row = connection.execute(
            "SELECT hold_status, released_at FROM archive_legal_holds "
            "WHERE document_id = %s AND authority_reference = 'CASE-OWNER'",
            (held_id,),
        ).fetchone()
        purge_row = connection.execute(
            "SELECT purge_status, purge_started_at, purged_at FROM archive_documents "
            "WHERE document_id = %s",
            (purge_id,),
        ).fetchone()
    assert foreign_holds == (0,)
    assert owner_hold_row == ("active", None)
    assert purge_row == ("not_eligible", None, None)
    assert object_path.is_file()

    traces = {
        f"trace-pg-{scope_name}-{operation}"
        for operation in ("access", "source-events", "hold", "release", "purge")
    }
    events = [
        event
        for document_id in (held_id, purge_id)
        for event in service.audit_repository.list_by_document_id(document_id)
        if event.trace_id in traces
    ]
    assert {event.trace_id for event in events} == traces
    assert all(event.authorization_decision is AuthorizationDecision.DENIED for event in events)


def test_postgres_legacy_cross_scope_chain_refuses_reads_and_replay_without_mutation(
    tmp_path: Path,
) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix="pg-legacy-source")
            target_id = _create_document(client, suffix="pg-legacy-target")
            foreign_current_id = _create_document(
                client,
                suffix="pg-legacy-foreign-current",
                tenant_id="tenant-other",
            )
            _persist_legacy_transition(
                service,
                source_document_id=source_id,
                target_document_id=target_id,
                suffix="pg-source-target",
            )
            _persist_legacy_transition(
                service,
                source_document_id=target_id,
                target_document_id=foreign_current_id,
                suffix="pg-target-foreign",
            )
            current = client.get(
                f"/documents/{source_id}/current",
                headers=_headers(trace_id="trace-pg-legacy-current"),
            )
            source_events = client.get(
                f"/documents/{source_id}/source-events",
                headers=_headers(trace_id="trace-pg-legacy-source-events"),
            )
            replay = client.post(
                f"/documents/{source_id}/supersede",
                json={
                    "target_document_id": target_id,
                    "transition_reason": "Retry persisted legacy transition",
                },
                headers=_headers(trace_id="trace-pg-legacy-replay"),
            )
    finally:
        app.dependency_overrides.clear()

    assert [current.status_code, source_events.status_code, replay.status_code] == [403] * 3
    assert all(
        foreign_current_id not in response.text for response in (current, source_events, replay)
    )
    with psycopg.connect(DATABASE_URL) as connection:
        relationships = connection.execute(
            "SELECT source_document_id, target_document_id "
            "FROM archive_lifecycle_relationships ORDER BY source_document_id"
        ).fetchall()
        pointers = connection.execute(
            "SELECT document_id, superseded_by_document_id FROM archive_documents "
            "WHERE document_id IN (%s, %s, %s) ORDER BY document_id",
            (source_id, target_id, foreign_current_id),
        ).fetchall()
    assert set(relationships) == {(source_id, target_id), (target_id, foreign_current_id)}
    assert dict(pointers) == {
        source_id: target_id,
        target_id: foreign_current_id,
        foreign_current_id: None,
    }
    traces = {
        "trace-pg-legacy-current",
        "trace-pg-legacy-source-events",
        "trace-pg-legacy-replay",
    }
    events = [
        event
        for event in service.audit_repository.list_by_document_id(foreign_current_id)
        if event.trace_id in traces
    ]
    assert {event.trace_id for event in events} == traces
    assert all(event.authorization_decision is AuthorizationDecision.DENIED for event in events)


@pytest.mark.parametrize("transition", ["supersede", "correct", "reissue"])
@pytest.mark.parametrize(
    ("tenant_id", "region"),
    [("tenant-other", "SG"), ("tenant-private-bank", "EMEA")],
)
def test_postgres_lifecycle_denial_preserves_both_documents_and_relationship_table(
    tmp_path: Path,
    transition: str,
    tenant_id: str,
    region: str,
) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix=f"pg-{transition}-source")
            target_id = _create_document(client, suffix=f"pg-{transition}-target")
            response = client.post(
                f"/documents/{source_id}/{transition}",
                json={
                    "target_document_id": target_id,
                    "transition_reason": "Foreign lifecycle request",
                },
                headers=_headers(tenant_id=tenant_id, region=region),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    with psycopg.connect(DATABASE_URL) as connection:
        relationship_count = connection.execute(
            "SELECT count(*) FROM archive_lifecycle_relationships"
        ).fetchone()
        rows = connection.execute(
            "SELECT document_id, superseded_by_document_id, supersedes_document_id, "
            "correction_of_document_id, reissue_of_document_id FROM archive_documents "
            "WHERE document_id IN (%s, %s) ORDER BY document_id",
            (source_id, target_id),
        ).fetchall()
    assert relationship_count == (0,)
    assert len(rows) == 2
    assert all(row[1:] == (None, None, None, None) for row in rows)


@pytest.mark.parametrize("transition", ["supersede", "correct", "reissue"])
def test_postgres_lifecycle_authorizes_target_before_mutation_and_replay(
    tmp_path: Path,
    transition: str,
) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix=f"pg-{transition}-owner-source")
            target_id = _create_document(
                client,
                suffix=f"pg-{transition}-foreign-target",
                tenant_id="tenant-other",
            )
            response = client.post(
                f"/documents/{source_id}/{transition}",
                json={
                    "target_document_id": target_id,
                    "transition_reason": "Cross-tenant target request",
                },
                headers=_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    with psycopg.connect(DATABASE_URL) as connection:
        relationship_count = connection.execute(
            "SELECT count(*) FROM archive_lifecycle_relationships"
        ).fetchone()
        pointers = connection.execute(
            "SELECT superseded_by_document_id, supersedes_document_id, "
            "correction_of_document_id, reissue_of_document_id FROM archive_documents "
            "WHERE document_id IN (%s, %s)",
            (source_id, target_id),
        ).fetchall()
    assert relationship_count == (0,)
    assert all(row == (None, None, None, None) for row in pointers)


@pytest.mark.parametrize("transition", ["supersede", "correct", "reissue"])
def test_postgres_lifecycle_owner_replay_converges_but_foreign_replay_is_denied(
    tmp_path: Path,
    transition: str,
) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            source_id = _create_document(client, suffix=f"pg-{transition}-replay-source")
            target_id = _create_document(client, suffix=f"pg-{transition}-replay-target")
            request_body = {
                "target_document_id": target_id,
                "transition_reason": "Approved lifecycle request",
            }
            first = client.post(
                f"/documents/{source_id}/{transition}",
                json=request_body,
                headers=_headers(),
            )
            foreign_replay = client.post(
                f"/documents/{source_id}/{transition}",
                json=request_body,
                headers=_headers(tenant_id="tenant-other"),
            )
            owner_replay = client.post(
                f"/documents/{source_id}/{transition}",
                json=request_body,
                headers=_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 201
    assert foreign_replay.status_code == 403
    assert owner_replay.status_code == 201
    assert (
        owner_replay.json()["lifecycle_relationship_id"]
        == first.json()["lifecycle_relationship_id"]
    )
    with psycopg.connect(DATABASE_URL) as connection:
        relationship_count = connection.execute(
            "SELECT count(*) FROM archive_lifecycle_relationships"
        ).fetchone()
    assert relationship_count == (1,)
