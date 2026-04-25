from pathlib import Path

import pytest

from app.archive.checksum import calculate_checksum, calculate_stream_checksum
from app.archive.exceptions import DocumentChecksumMismatchError, StorageReadFailedError
from app.archive.storage import FilesystemObjectStorage


def test_filesystem_storage_validates_checksum_before_write(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)

    with pytest.raises(DocumentChecksumMismatchError):
        storage.put(
            key="sg/tenant/report/doc.pdf",
            content=b"content",
            expected_checksum="0" * 64,
            checksum_algorithm="sha256",
        )

    assert not (tmp_path / "sg" / "tenant" / "report" / "doc.pdf").exists()


def test_filesystem_storage_round_trips_content(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    content = b"rendered-pdf"
    stored = storage.put(
        key="sg/tenant/report/doc.pdf",
        content=content,
        expected_checksum=calculate_checksum(content),
        checksum_algorithm="sha256",
    )

    assert stored.size_bytes == len(content)
    assert storage.get(key=stored.key) == content


def test_filesystem_storage_rejects_missing_or_unsafe_reads(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)

    with pytest.raises(StorageReadFailedError):
        storage.get(key="missing.pdf")

    with pytest.raises(StorageReadFailedError):
        storage.get(key="../secret.pdf")


def test_checksum_helpers_reject_unsupported_algorithms() -> None:
    with pytest.raises(ValueError):
        calculate_checksum(b"content", algorithm="md5")

    with pytest.raises(ValueError):
        calculate_stream_checksum([b"con", b"tent"], algorithm="md5")


def test_stream_checksum_matches_single_buffer_checksum() -> None:
    assert calculate_stream_checksum([b"con", b"tent"]) == calculate_checksum(b"content")
