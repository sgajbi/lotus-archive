"""Custody is verified, idempotent, and identity-honest (archive#118).

The evidence chain's missing link: Report mints the governed
`document_reference`, Render prints it in the footer and produces exact bytes
with a raw SHA - and only Archive's verified custody makes "delivered" mean
"recoverable as the exact bytes delivered". These tests hold the contract's
acceptance list, one behaviour each.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.archive.archive_writer import ArchiveWriter
from app.archive.exceptions import (
    ArtifactIdentityCollisionError,
    DeclaredChecksumMismatchError,
)
from app.archive.models import ArchiveDocumentInput
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.storage import FilesystemObjectStorage
from tests.unit.test_archive_writer import valid_metadata_input

ARTIFACT = b"%PDF-1.7 exact client bytes"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT).hexdigest()


def _writer(tmp_path: Path) -> tuple[ArchiveWriter, InMemoryArchiveDocumentRepository]:
    repository = InMemoryArchiveDocumentRepository()
    return ArchiveWriter(
        repository=repository,
        storage=FilesystemObjectStorage(tmp_path / "objects"),
    ), repository


def _custody_input(**overrides: object) -> ArchiveDocumentInput:
    values: dict[str, object] = {
        "document_reference": "rdoc_11111111-1111-5111-8111-111111111111",
        "declared_artifact_sha256": ARTIFACT_SHA,
        "render_runtime_engine": "typst",
        "render_runtime_engine_version": "0.13",
        "template_digest": "sha256:template-digest",
    }
    values.update(overrides)
    return valid_metadata_input(**values)


def test_verified_custody_persists_the_exact_bytes_with_both_identities(tmp_path: Path) -> None:
    """The happy path holds every custody fact at once: the declared digest
    matched what arrived, the stored record carries the governed reference
    AND Archive's own id (two facts, never collapsed), the provenance rides
    along, and retrieval is byte-identical - proven by re-hashing what the
    storage hands back, not by trusting metadata."""

    writer, _repository = _writer(tmp_path)
    storage = writer.storage

    metadata = writer.archive_document(metadata_input=_custody_input(), content=ARTIFACT)

    assert metadata.document_id.startswith("doc_")
    assert metadata.document_reference == "rdoc_11111111-1111-5111-8111-111111111111"
    assert metadata.declared_artifact_sha256 == ARTIFACT_SHA
    assert metadata.checksum == ARTIFACT_SHA
    assert metadata.render_runtime_engine == "typst"
    round_trip = storage.get(key=metadata.storage_key)
    assert hashlib.sha256(round_trip).hexdigest() == ARTIFACT_SHA


def test_a_false_declaration_is_refused_before_anything_is_stored(tmp_path: Path) -> None:
    """A stored artifact whose declared and computed identities disagree
    would be corruption wearing a certificate. The refusal names BOTH hashes
    - the operator must see what was claimed and what was measured - and
    nothing is orphaned: no custody record, no stored object."""

    writer, repository = _writer(tmp_path)
    wrong = "0" * 64

    with pytest.raises(DeclaredChecksumMismatchError) as caught:
        writer.archive_document(
            metadata_input=_custody_input(declared_artifact_sha256=wrong),
            content=ARTIFACT,
        )

    assert wrong in str(caught.value)
    assert ARTIFACT_SHA in str(caught.value)
    assert repository.get_by_checksum(ARTIFACT_SHA) == []
    assert list((tmp_path / "objects").rglob("*")) == []


def test_truncated_and_empty_bytes_fail_the_same_declaration(tmp_path: Path) -> None:
    """A wrong artifact is a wrong artifact regardless of how it got short:
    truncation and zero-length are ordinary mismatches, not special cases."""

    writer, _repository = _writer(tmp_path)

    with pytest.raises(DeclaredChecksumMismatchError):
        writer.archive_document(metadata_input=_custody_input(), content=ARTIFACT[:7])
    with pytest.raises(DeclaredChecksumMismatchError):
        writer.archive_document(metadata_input=_custody_input(), content=b"")


def test_redelivery_of_the_same_artifact_converges_on_one_custody_record(
    tmp_path: Path,
) -> None:
    """The lost-response case: Render's derived request id makes a retry
    arrive as the same request, and Archive returns the SAME durable record -
    one artifact, one custody, however many deliveries."""

    writer, repository = _writer(tmp_path)

    first = writer.archive_document(metadata_input=_custody_input(), content=ARTIFACT)
    second = writer.archive_document(metadata_input=_custody_input(), content=ARTIFACT)

    assert second.document_id == first.document_id
    assert len(repository.get_by_checksum(ARTIFACT_SHA)) == 1


def test_a_regenerate_is_a_distinct_custody_record_under_the_same_reference(
    tmp_path: Path,
) -> None:
    """Two renders under one governed reference are two artifacts (different
    raw SHA by design - only original bytes carry exact identity). Both are
    held, both retrievable, distinguished by SHA."""

    writer, repository = _writer(tmp_path)
    regenerated = b"%PDF-1.7 regenerated bytes"
    regenerated_sha = hashlib.sha256(regenerated).hexdigest()

    first = writer.archive_document(metadata_input=_custody_input(), content=ARTIFACT)
    second = writer.archive_document(
        metadata_input=_custody_input(
            archive_request_id="archive-request-regenerate",
            declared_artifact_sha256=regenerated_sha,
        ),
        content=regenerated,
    )

    assert second.document_id != first.document_id
    assert first.document_reference == second.document_reference
    assert {first.checksum, second.checksum} == {ARTIFACT_SHA, regenerated_sha}


def test_the_same_bytes_under_a_different_reference_are_refused(tmp_path: Path) -> None:
    """One artifact answers one governed question. The identical bytes
    arriving under a second document reference signal an upstream identity
    fault - surfaced with both references named, never stored twice."""

    writer, _repository = _writer(tmp_path)
    writer.archive_document(metadata_input=_custody_input(), content=ARTIFACT)

    with pytest.raises(ArtifactIdentityCollisionError) as caught:
        writer.archive_document(
            metadata_input=_custody_input(
                archive_request_id="archive-request-collision",
                document_reference="rdoc_22222222-2222-5222-8222-222222222222",
            ),
            content=ARTIFACT,
        )

    message = str(caught.value)
    assert "rdoc_11111111-1111-5111-8111-111111111111" in message
    assert "rdoc_22222222-2222-5222-8222-222222222222" in message


def test_legacy_relay_deliveries_without_custody_fields_still_archive(tmp_path: Path) -> None:
    """The cutover is a migration with no dual-write window, but the fields
    must stay additive until the relay retires: a delivery declaring nothing
    is stored exactly as before, with Archive's own computed checksum as the
    only integrity fact."""

    writer, _repository = _writer(tmp_path)

    metadata = writer.archive_document(
        metadata_input=valid_metadata_input(),
        content=ARTIFACT,
    )

    assert metadata.document_reference is None
    assert metadata.declared_artifact_sha256 is None
    assert metadata.checksum == ARTIFACT_SHA


def test_template_publication_posture_rides_custody_verbatim(tmp_path: Path) -> None:
    """Render's governed template posture at render time is stored and echoed
    with the custody record (render#120 publication gating): Report's
    external gate reads archived_verified AND template_publication ==
    "published" - never digests. Archive stores the posture verbatim,
    bounded to the owner's vocabulary, and never interprets it."""

    writer, _repository = _writer(tmp_path)

    published = writer.archive_document(
        metadata_input=_custody_input(template_publication="Published"),
        content=ARTIFACT,
    )
    assert published.template_publication == "published"

    legacy = writer.archive_document(
        metadata_input=valid_metadata_input(archive_request_id="archive-request-legacy-tp"),
        content=b"%PDF-1.7 legacy bytes",
    )
    assert legacy.template_publication is None

    with pytest.raises(ValidationError):
        _custody_input(template_publication="beta")


def test_declared_digest_refuses_anything_but_a_sha256_hex_digest() -> None:
    """A declaration that is not a 64-hex digest can never match a computed
    SHA-256; refusing it at the model boundary names the fault precisely
    instead of reporting a mismatch against garbage."""

    for invalid in ("sha256:short", "g" * 64, "0" * 63):
        with pytest.raises(ValidationError):
            _custody_input(declared_artifact_sha256=invalid)


def test_declared_digest_accepts_the_prefixed_form_and_normalizes(tmp_path: Path) -> None:
    """Render's envelope carries `sha256:<hex>`; the prefix is accepted and
    stripped so both callers can state the same fact in their own notation
    without two fields existing for it."""

    writer, _repository = _writer(tmp_path)

    metadata = writer.archive_document(
        metadata_input=_custody_input(declared_artifact_sha256=f"sha256:{ARTIFACT_SHA.upper()}"),
        content=ARTIFACT,
    )

    assert metadata.declared_artifact_sha256 == ARTIFACT_SHA
