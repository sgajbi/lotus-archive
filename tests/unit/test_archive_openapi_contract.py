from app.archive.api import ARCHIVE_API_TAG
from app.main import app


def test_archive_document_api_openapi_contract_is_certification_ready() -> None:
    spec = app.openapi()

    expected_operations = {
        ("/documents", "post"): "Archive a generated document",
        ("/documents/{document_id}", "get"): "Get archived document metadata",
        ("/documents/{document_id}/current", "get"): "Get current document in lifecycle",
        ("/documents/{document_id}/source-events", "get"): ("List archived document source events"),
        ("/documents/{document_id}/idea-lifecycle-decisions", "post"): (
            "Issue an authenticated Idea evidence lifecycle decision"
        ),
        ("/documents/{document_id}/download", "get"): "Download an archived document",
        ("/documents/{document_id}/access-events", "get"): "List document access events",
        ("/documents/{document_id}/retention", "get"): "Get document retention posture",
        ("/documents/{document_id}/purge-evaluation", "post"): (
            "Evaluate document purge eligibility"
        ),
        ("/documents/{document_id}/purge", "post"): "Execute document purge",
        ("/documents/{document_id}/legal-holds", "post"): "Set a document legal hold",
        ("/documents/{document_id}/legal-holds/{legal_hold_id}", "delete"): (
            "Release a document legal hold"
        ),
        ("/documents/{document_id}/supersede", "post"): "Supersede an archived document",
        ("/documents/{document_id}/correct", "post"): "Correct an archived document",
        ("/documents/{document_id}/reissue", "post"): "Reissue an archived document",
    }
    for (path, method), summary in expected_operations.items():
        operation = spec["paths"][path][method]
        assert operation["summary"] == summary
        assert ARCHIVE_API_TAG in operation["tags"]
        assert len(operation["description"]) > 80
        assert "401" in operation["responses"]
        assert "403" in operation["responses"]

    create_operation = spec["paths"]["/documents"]["post"]
    assert "ArchiveDocumentCreateRequest" in str(create_operation["requestBody"])
    assert "201" in create_operation["responses"]
    assert "409" in create_operation["responses"]

    purge_operation = spec["paths"]["/documents/{document_id}/purge"]["post"]
    assert "409" in purge_operation["responses"]

    legal_hold_operation = spec["paths"]["/documents/{document_id}/legal-holds"]["post"]
    assert "LegalHoldCreateRequest" in str(legal_hold_operation["requestBody"])

    supersede_operation = spec["paths"]["/documents/{document_id}/supersede"]["post"]
    assert "LifecycleTransitionRequest" in str(supersede_operation["requestBody"])
    assert "409" in supersede_operation["responses"]

    metadata_schema = spec["components"]["schemas"]["ArchiveDocumentResponse"]["properties"]
    assert metadata_schema["document_id"]["description"]
    assert metadata_schema["checksum"]["description"]
    assert metadata_schema["reviewed_advisory_narrative"]["description"]
    assert metadata_schema["idea_evidence_pack"]["description"]
    assert "storage_key" not in metadata_schema

    narrative_schema = spec["components"]["schemas"]["ReviewedAdvisoryNarrativeArchiveSummary"][
        "properties"
    ]
    assert narrative_schema["package_id"]["minLength"] == 1
    assert narrative_schema["source_narrative_hash"]["description"].startswith("SHA-256")
    assert "PDF render" in narrative_schema["included_in_render"]["description"]

    idea_schema = spec["components"]["schemas"]["IdeaEvidencePackArchiveSummary"]["properties"]
    assert idea_schema["report_evidence_pack_id"]["minLength"] == 1
    assert idea_schema["source_contract_version"]["const"] == (
        "lotus_idea_evidence_pack_report_input.v1"
    )
    assert idea_schema["client_publication_authority_granted"]["const"] is False

    retention_schema = spec["components"]["schemas"]["RetentionResponse"]["properties"]
    assert retention_schema["purge_status"]["description"]
    assert retention_schema["legal_hold_count"]["description"]

    lifecycle_schema = spec["components"]["schemas"]["LifecycleRelationshipResponse"]["properties"]
    assert lifecycle_schema["transition_type"]["description"]
    assert lifecycle_schema["current_document_id"]["description"]

    source_events_schema = spec["components"]["schemas"]["ArchiveDocumentSourceEventsResponse"][
        "properties"
    ]
    assert source_events_schema["no_raw_payloads"]["description"]
    assert source_events_schema["events"]["description"]
    assert source_events_schema["returned_count"]["description"]
    assert source_events_schema["total_count"]["description"]
    assert source_events_schema["next_offset"]["description"]
    assert source_events_schema["delivery_mode"]["description"]
    assert source_events_schema["replay_contract"]["description"]

    source_event_schema = spec["components"]["schemas"]["ArchiveDocumentSourceEvent"]["properties"]
    assert "transition_reason" not in source_event_schema
    assert source_event_schema["transition_reason_code"]["description"]
    assert source_event_schema["report_data_contract_version"]["description"]
    assert source_event_schema["template_id"]["description"]
    assert source_event_schema["source_owner"]["description"]

    access_events_schema = spec["components"]["schemas"]["AccessEventListResponse"]["properties"]
    assert access_events_schema["returned_count"]["description"]
    assert access_events_schema["total_count"]["description"]
    assert access_events_schema["next_offset"]["description"]

    for path in [
        "/documents/{document_id}/source-events",
        "/documents/{document_id}/access-events",
    ]:
        parameters = spec["paths"][path]["get"]["parameters"]
        names = {parameter["name"] for parameter in parameters}
        assert {"limit", "offset"} <= names


def test_version_endpoint_openapi_contract_is_support_ready() -> None:
    spec = app.openapi()

    operation = spec["paths"]["/version"]["get"]

    assert operation["summary"] == "Get runtime build metadata"
    assert "support diagnostics" in operation["description"]
    assert "operations" in operation["tags"]
    assert "BuildMetadata" in str(operation["responses"]["200"])

    schema = spec["components"]["schemas"]["BuildMetadata"]["properties"]
    for field in [
        "service",
        "version",
        "commit_sha",
        "repository_url",
        "git_ref",
        "build_timestamp_utc",
        "ci_run_id",
        "image_ref",
        "image_digest",
        "image_digest_posture",
    ]:
        assert schema[field]["description"]
