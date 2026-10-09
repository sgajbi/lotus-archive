"""Source-shaped synthetic metadata; never a claim of live producer acceptance."""

from hashlib import sha256

from tests.unit.test_archive_writer import valid_metadata_input


def composite_metadata(content: bytes, revision: str = "original") -> dict[str, object]:
    metadata = valid_metadata_input().model_dump(mode="json")
    metadata.update(
        {
            "archive_request_id": f"archive-composite-{revision}",
            "report_job_id": f"report-composite-{revision}",
            "snapshot_id": f"snapshot-composite-{revision}",
            "render_job_id": f"render-composite-{revision}",
            "render_attempt_id": f"render-composite-{revision}:{sha256(content).hexdigest()[:16]}",
            "report_type": "composite_review",
            "portfolio_scope": "composite",
            "portfolio_id": None,
            "composite_id": "NEUTRAL_BALANCED",
            "client_reference": None,
            "as_of_date": "2026-01-31",
            "reporting_period_start": "2026-01-01",
            "reporting_period_end": "2026-01-31",
            "frequency": "monthly",
            "template_id": "composite-review",
            "template_version": "v1",
            "report_data_contract_version": "composite_review.v1",
            "output_format": "xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "document_reference": "composite-question-january",
            "report_revision_id": f"rrv3:{revision}",
            "declared_artifact_sha256": sha256(content).hexdigest(),
            "composite_report_identity": {
                "contract_version": "composite_review.v1",
                "qualification": "EXPLICIT_RETAINED_CALCULATED_REPLAY",
                "publication_state": "NOT_ATTESTED",
                "series_digest": "a" * 64,
                "source_revision_digest": "b" * 64,
                "factual_content_digest": "c" * 64,
                "selection": {
                    "tenant_id": "tenant-private-bank",
                    "composite_id": "NEUTRAL_BALANCED",
                    "calculation_id": "00000000-0000-0000-0000-000000000099",
                    "period_start": "2026-01-01",
                    "period_end": "2026-01-31",
                    "reporting_currency": "USD",
                    "return_view": "NET_ACTUAL",
                    "methodology": "persisted_member_return_asset_weighted_twr_v1",
                    "engine_version": "synthetic-engine.v1",
                    "calculation_fingerprint": "sha256:" + "d" * 64,
                    "response_digest": "sha256:" + "e" * 64,
                    "windows": [
                        {
                            "materialization_id": "00000000-0000-0000-0000-000000000001",
                            "period_start": "2026-01-01",
                            "period_end": "2026-01-31",
                            "restatement_sequence": 1,
                            "definition_content_hash": "sha256:" + "a" * 64,
                            "membership_content_hash": "sha256:" + "b" * 64,
                            "attestation_content_hash": "sha256:" + "c" * 64,
                            "source_cut_id": "source-cut-1",
                            "method_binding": {
                                "method_id": "ASSET_WEIGHTED",
                                "method_version": "v1",
                            },
                            "retained_receipt_fingerprint": "sha256:" + "f" * 64,
                        }
                    ],
                },
            },
        }
    )
    return metadata
