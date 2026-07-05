from typing import cast

from app.archive.models import ArchiveDocumentMetadata, LifecycleTransitionType
import app.archive.source_events as source_events
from app.archive.source_events import build_archive_document_source_events
from tests.unit.test_archive_metadata_model import advisor_proposal_memo_summary
from tests.unit.test_archive_writer import valid_metadata_input


def test_source_events_include_advisor_proposal_memo_artifact_ref() -> None:
    metadata_input = valid_metadata_input(
        advisor_proposal_memo=advisor_proposal_memo_summary(),
    )
    metadata = ArchiveDocumentMetadata(
        **metadata_input.model_dump(),
        document_id="doc_memo",
        storage_provider="filesystem",
        storage_namespace="local-development",
        storage_key="sg/tenant-private-bank/portfolio_review/doc_memo.pdf",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        size_bytes=100,
    )

    events = build_archive_document_source_events(
        metadata=metadata,
        current_document_id=metadata.document_id,
        lifecycle_relationships=[],
    )

    reason_codes = cast(list[str], events[0]["reason_codes"])
    artifact_refs = cast(list[dict[str, str]], events[0]["artifact_refs"])

    assert "advisor_proposal_memo_archive_summary_preserved" in reason_codes
    assert {
        "artifact_type": "advisor_proposal_memo_package",
        "artifact_id": "memo-001",
        "content_hash": "sha256:" + "c" * 64,
    } in artifact_refs


def test_source_events_have_fallback_for_unknown_lifecycle_type() -> None:
    unknown = cast(LifecycleTransitionType, "unexpected")

    assert source_events._event_type_for_lifecycle(unknown) == (
        "generated_document_lifecycle_updated"
    )
