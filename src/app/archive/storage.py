from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.archive.checksum import calculate_checksum
from app.archive.exceptions import DocumentChecksumMismatchError, StorageReadFailedError


@dataclass(frozen=True)
class StoredObject:
    provider: str
    namespace: str
    key: str
    checksum_algorithm: str
    checksum: str
    size_bytes: int


class ObjectStorage(Protocol):
    provider: str
    namespace: str

    def put(
        self,
        *,
        key: str,
        content: bytes,
        expected_checksum: str,
        checksum_algorithm: str,
    ) -> StoredObject: ...

    def get(self, *, key: str) -> bytes: ...


class FilesystemObjectStorage:
    provider = "filesystem"

    def __init__(self, root: Path, *, namespace: str = "local-development") -> None:
        self.root = root
        self.namespace = namespace
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        key: str,
        content: bytes,
        expected_checksum: str,
        checksum_algorithm: str,
    ) -> StoredObject:
        actual_checksum = calculate_checksum(content, algorithm=checksum_algorithm)
        if actual_checksum != expected_checksum:
            raise DocumentChecksumMismatchError("document checksum did not match expected value")

        object_path = self._path_for_key(key)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = object_path.with_suffix(object_path.suffix + ".tmp")
        temporary_path.write_bytes(content)
        temporary_path.replace(object_path)

        return StoredObject(
            provider=self.provider,
            namespace=self.namespace,
            key=key,
            checksum_algorithm=checksum_algorithm,
            checksum=actual_checksum,
            size_bytes=len(content),
        )

    def get(self, *, key: str) -> bytes:
        object_path = self._path_for_key(key)
        if not object_path.exists():
            raise StorageReadFailedError("stored document object was not found")
        return object_path.read_bytes()

    def _path_for_key(self, key: str) -> Path:
        parts = Path(key).parts
        if ".." in parts or Path(key).is_absolute():
            raise StorageReadFailedError("unsafe storage key")
        return self.root.joinpath(*parts)
