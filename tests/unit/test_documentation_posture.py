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

    assert "No client-facing archive product feature is supported yet." in supported_features
    assert "| Generated-document archival | `not_supported` |" in supported_features
    assert "| Controlled document download or signed URL issuance | `not_supported` |" in (
        supported_features
    )
    assert "| Arbitrary file storage | `not_supported` |" in supported_features


def test_archive_boundary_doc_rejects_local_output_directory_architecture() -> None:
    boundary_doc = " ".join(
        _read("docs/architecture/archive-service-boundaries.md").lower().split()
    )

    assert "general-purpose file store" in boundary_doc
    assert "postgresql metadata plus s3-compatible object storage" in boundary_doc
    assert "local filesystem storage must not become product architecture" in boundary_doc
