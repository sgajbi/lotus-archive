from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_docs_do_not_contain_scaffold_placeholders() -> None:
    docs = "\n".join(
        [
            _read("README.md"),
            _read("wiki/Home.md"),
            _read("docs/runbooks/service-operations.md"),
            _read("docs/supported-features.md"),
            _read("docs/architecture/archive-service-boundaries.md"),
        ]
    ).lower()

    assert "replace this page" not in docs
    assert "todo" not in docs
    assert "coming soon" not in docs


def test_supported_features_baseline_blocks_client_feature_overclaim() -> None:
    supported_features = _read("docs/supported-features.md")

    assert "Workbench-facing archive retrieval is not supported yet." in (supported_features)
    assert "| Generated-document archival | `ready` |" in supported_features
    assert "| Controlled document binary download | `ready` |" in supported_features
    assert "| Report-to-archive handoff | `ready` |" in supported_features
    assert "| Gateway-backed document retrieval | `ready` |" in supported_features
    assert "| Report-to-archive handoff | `not_supported` |" not in supported_features
    assert "| Workbench document retrieval surface | `not_supported` |" in supported_features
    assert "| Arbitrary file storage | `not_supported` |" in supported_features


def test_operator_docs_match_report_handoff_and_gateway_retrieval_support() -> None:
    docs = "\n".join(
        [
            _read("README.md"),
            _read("docs/runbooks/service-operations.md"),
            _read("docs/supported-features.md"),
            _read("docs/architecture/archive-service-boundaries.md"),
        ]
    )

    assert "report-to-archive handoff through `lotus-report`" in docs
    assert "Gateway-backed product retrieval is implemented in `lotus-gateway`" in docs
    assert "Gateway-backed product retrieval remains future work" not in docs
    assert "Do not use this service for report handoff" not in docs


def test_archive_boundary_doc_rejects_local_output_directory_architecture() -> None:
    boundary_doc = " ".join(
        _read("docs/architecture/archive-service-boundaries.md").lower().split()
    )

    assert "general-purpose file store" in boundary_doc
    assert "postgresql metadata plus s3-compatible object storage" in boundary_doc
    assert "local filesystem storage must not become product architecture" in boundary_doc
