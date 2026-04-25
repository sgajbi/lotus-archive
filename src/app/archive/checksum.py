from __future__ import annotations

from collections.abc import Iterable
import hashlib

SUPPORTED_CHECKSUM_ALGORITHM = "sha256"


class UnsupportedChecksumAlgorithmError(ValueError):
    pass


def calculate_checksum(content: bytes, *, algorithm: str = SUPPORTED_CHECKSUM_ALGORITHM) -> str:
    normalized = algorithm.lower()
    if normalized != SUPPORTED_CHECKSUM_ALGORITHM:
        raise UnsupportedChecksumAlgorithmError(f"Unsupported checksum algorithm: {algorithm}")
    return hashlib.sha256(content).hexdigest()


def calculate_stream_checksum(
    chunks: Iterable[bytes],
    *,
    algorithm: str = SUPPORTED_CHECKSUM_ALGORITHM,
) -> str:
    normalized = algorithm.lower()
    if normalized != SUPPORTED_CHECKSUM_ALGORITHM:
        raise UnsupportedChecksumAlgorithmError(f"Unsupported checksum algorithm: {algorithm}")
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()
