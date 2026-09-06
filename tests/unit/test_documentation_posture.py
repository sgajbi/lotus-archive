import tomllib
import json
import re
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


def test_supported_features_baseline_blocks_direct_workbench_overclaim() -> None:
    supported_features = _read("docs/supported-features.md")

    assert "Workbench-facing archive retrieval is supported only through" in (supported_features)
    assert "| Generated-document archival | `ready` |" in supported_features
    assert "| Controlled document binary download | `ready` |" in supported_features
    assert "| Archive document source events | `ready` |" in supported_features
    assert "| Report-to-archive handoff | `ready` |" in supported_features
    assert "| Gateway-backed document retrieval | `ready` |" in supported_features
    assert "| Gateway-backed Workbench document retrieval | `ready` |" in supported_features
    assert "| Reviewed advisory narrative archive summary | `ready` |" in supported_features
    assert "| Production durable archive runtime | `ready` |" in supported_features
    assert "PostgreSQL metadata/audit plus S3-compatible storage" in supported_features
    assert "| Dependency vulnerability exceptions | `ready` |" in supported_features
    assert "| Report-to-archive handoff | `not_supported` |" not in supported_features
    assert "| Direct Workbench archive calls | `not_supported` |" in supported_features
    assert "| Client-ready advisory narrative publication | `not_supported` |" in supported_features
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
    assert "lotus-archive.generated_document_client_communication.v1" in docs
    assert "pull-only" in docs
    assert "raw lifecycle reason text" in docs
    assert "report-input provenance" in docs
    assert "Gateway-backed product retrieval remains future work" not in docs
    assert "Do not use this service for report handoff" not in docs


def test_archive_boundary_doc_rejects_local_output_directory_architecture() -> None:
    boundary_doc = " ".join(
        _read("docs/architecture/archive-service-boundaries.md").lower().split()
    )

    assert "general-purpose file store" in boundary_doc
    assert "postgresql metadata plus s3-compatible object storage" in boundary_doc
    assert "local filesystem storage must not become product architecture" in boundary_doc


def test_local_enterprise_refactor_playbook_is_only_canonical_pointer() -> None:
    local_playbook = _read("docs/architecture/ENTERPRISE_BACKEND_REFACTORING_INSTRUCTIONS.md")
    repo_docs = "\n".join([_read("README.md"), _read("REPOSITORY-ENGINEERING-CONTEXT.md")])

    assert "lotus-platform/context/playbooks/ENTERPRISE-BACKEND-REFACTORING-INSTRUCTIONS.md" in (
        local_playbook
    )
    assert "stale local copy" in " ".join(local_playbook.split())
    assert "# 6. Layer Responsibilities" not in local_playbook
    assert "runtime composition settings" in repo_docs


def _repository_slug() -> str:
    """This repository's name, from the packaging metadata.

    Checked in, so it needs no git remote and no CI environment -- a source
    snapshot or a checkout with no origin still runs this gate. Load-bearing for
    packaging, so it cannot be silently wrong. And outside the governance file
    set, so it stays independent of the policy document: deriving identity from
    the document would let a wholly copied table agree with itself, and a
    hand-written constant here would repeat the per-repo edit whose omission
    caused the defect this test exists for.
    """
    with (ROOT / "pyproject.toml").open("rb") as handle:
        name = tomllib.load(handle)["project"]["name"]
    assert name, "pyproject [project] name is empty"
    return name


def test_branch_protection_policy_table_describes_this_repository() -> None:
    """The lifted checker is byte-identical everywhere; the policy table is not.

    Two of the three adopters shipped a stated limitation describing a
    ``Risk-only`` fork, copied from the first adoption. A limitation that names
    the wrong repository is evidence the text was never read in the context it
    governs, which is the exact failure the table exists to prevent.

    Asserted POSITIVELY on the identity-bearing fields rather than by scanning
    for foreign names: a blanket scan would reject the canonical references the
    table legitimately cites, and would need a list of sibling repositories that
    drifts as the estate grows.

    Interim: a canonical check would remove the need for this per-repo guard.
    Filed as lotus-gateway#745.
    """
    slug = _repository_slug()
    policy = _read("quality/branch_protection_policy.v1.json")
    document = json.loads(policy)

    assert document["repository"].endswith(f"/{slug}"), (
        f"policy repository is {document['repository']!r} in the {slug} package"
    )

    review_lead = document["review_authority"]["review_lead"]
    assert slug in review_lead, f"review_lead does not name {slug}: {review_lead!r}"

    expected = slug.removeprefix("lotus-").capitalize()
    named = {m.group(1) for m in re.finditer("(?<![A-Za-z])([A-Z][a-z]+)-only", policy)}
    foreign = sorted(named - {expected})
    assert not foreign, f"policy table for {slug} describes another repository: {foreign}"
