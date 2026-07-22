from typing import cast

from app.archive.models import ArchiveDocumentMetadata, LifecycleTransitionType
import app.archive.source_events as source_events
from app.archive.source_events import build_archive_document_source_events
from tests.unit.test_archive_metadata_model import (
    advisor_proposal_memo_summary,
    idea_evidence_pack_summary,
)
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


def test_source_events_include_idea_evidence_pack_artifact_refs() -> None:
    metadata_input = valid_metadata_input(
        report_type="proof_pack",
        template_id="proof-pack",
        report_data_contract_version="dpm_proof_pack_report_input.v1",
        idea_evidence_pack=idea_evidence_pack_summary(),
    )
    metadata = ArchiveDocumentMetadata(
        **metadata_input.model_dump(),
        document_id="doc_idea_evidence_pack",
        storage_provider="filesystem",
        storage_namespace="local-development",
        storage_key="sg/tenant-private-bank/proof_pack/doc_idea_evidence_pack.pdf",
        checksum_algorithm="sha256",
        checksum="b" * 64,
        size_bytes=100,
    )

    events = build_archive_document_source_events(
        metadata=metadata,
        current_document_id=metadata.document_id,
        lifecycle_relationships=[],
    )

    reason_codes = cast(list[str], events[0]["reason_codes"])
    artifact_refs = cast(list[dict[str, str]], events[0]["artifact_refs"])

    assert "idea_evidence_pack_archive_summary_preserved" in reason_codes
    assert {
        "artifact_type": "idea_evidence_pack",
        "artifact_id": "ievp_001",
        "content_hash": "sha256:" + "e" * 64,
    } in artifact_refs
    assert {
        "artifact_type": "report_evidence_pack",
        "artifact_id": "irep_001",
        "content_hash": "sha256:" + "e" * 64,
    } in artifact_refs


def test_source_events_have_fallback_for_unknown_lifecycle_type() -> None:
    unknown = cast(LifecycleTransitionType, "unexpected")

    assert source_events._event_type_for_lifecycle(unknown) == (
        "generated_document_lifecycle_updated"
    )
