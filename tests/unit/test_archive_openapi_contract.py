from app.archive.api import ARCHIVE_API_TAG
from app.main import app


def test_archive_document_api_openapi_contract_is_certification_ready() -> None:
    spec = app.openapi()

    expected_operations = {
        ("/documents", "post"): "Archive a generated document",
        ("/documents/{document_id}", "get"): "Get archived document metadata",
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

    metadata_schema = spec["components"]["schemas"]["ArchiveDocumentResponse"]["properties"]
    assert metadata_schema["document_id"]["description"]
    assert metadata_schema["checksum"]["description"]
    assert "storage_key" not in metadata_schema

    retention_schema = spec["components"]["schemas"]["RetentionResponse"]["properties"]
    assert retention_schema["purge_status"]["description"]
    assert retention_schema["legal_hold_count"]["description"]
