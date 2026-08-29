from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.archive.checksum import calculate_checksum
from app.archive.exceptions import (
    DocumentChecksumMismatchError,
    StorageReadFailedError,
    StorageWriteFailedError,
)
from app.archive.s3_storage import S3ObjectStorage


class FakeS3Client:
    def __init__(self) -> None:
        self.put_request: dict[str, object] | None = None
        self.get_response: Mapping[str, object] = {"Body": BytesIO(b"archived")}
        self.deleted_key: str | None = None
        self.error: ClientError | None = None
        self.head_bucket_request: dict[str, object] | None = None

    def head_bucket(self, **kwargs: object) -> Mapping[str, object]:
        if self.error is not None:
            raise self.error
        self.head_bucket_request = kwargs
        return {}

    def put_object(self, **kwargs: object) -> Mapping[str, object]:
        if self.error is not None:
            raise self.error
        self.put_request = kwargs
        return {}

    def get_object(self, **kwargs: object) -> Mapping[str, object]:
        if self.error is not None:
            raise self.error
        return self.get_response

    def delete_object(self, **kwargs: object) -> Mapping[str, object]:
        if self.error is not None:
            raise self.error
        self.deleted_key = str(kwargs["Key"])
        return {}


def _storage(client: FakeS3Client) -> S3ObjectStorage:
    return S3ObjectStorage(
        bucket="lotus-archive",
        namespace="sg-production",
        key_prefix="generated-documents",
        region="ap-southeast-1",
        endpoint_url=None,
        server_side_encryption="aws:kms",
        kms_key_id="alias/lotus-archive",
        client=client,
    )


def test_s3_storage_writes_checksum_and_encryption_evidence() -> None:
    client = FakeS3Client()
    storage = _storage(client)
    content = b"archived"

    stored = storage.put(
        key="sg/tenant/document.pdf",
        content=content,
        expected_checksum=calculate_checksum(content),
        checksum_algorithm="sha256",
    )

    assert stored.provider == "s3"
    assert stored.namespace == "sg-production"
    assert client.put_request is not None
    assert client.put_request["Bucket"] == "lotus-archive"
    assert client.put_request["Key"] == "generated-documents/sg/tenant/document.pdf"
    assert client.put_request["ServerSideEncryption"] == "aws:kms"
    assert client.put_request["SSEKMSKeyId"] == "alias/lotus-archive"
    assert client.put_request["ChecksumSHA256"]


def test_s3_storage_readiness_measures_bucket_access() -> None:
    client = FakeS3Client()
    storage = _storage(client)

    storage.check_ready()

    assert client.head_bucket_request == {"Bucket": "lotus-archive"}

    client.error = ClientError({"Error": {"Code": "AccessDenied"}}, "HeadBucket")
    with pytest.raises(RuntimeError, match="archive_storage_unavailable"):
        storage.check_ready()


def test_s3_storage_rejects_blank_bucket() -> None:
    with pytest.raises(ValueError, match="bucket must not be blank"):
        S3ObjectStorage(
            bucket=" ",
            namespace="sg-production",
            key_prefix="archive",
            region=None,
            endpoint_url=None,
            server_side_encryption="AES256",
            kms_key_id=None,
            client=FakeS3Client(),
        )


def test_s3_storage_round_trips_and_deletes_object() -> None:
    client = FakeS3Client()
    storage = _storage(client)

    assert storage.get(key="sg/tenant/document.pdf") == b"archived"
    storage.delete(key="sg/tenant/document.pdf")

    assert client.deleted_key == "generated-documents/sg/tenant/document.pdf"


def test_s3_storage_fails_closed_for_checksum_and_provider_errors() -> None:
    client = FakeS3Client()
    storage = _storage(client)

    with pytest.raises(DocumentChecksumMismatchError):
        storage.put(
            key="document.pdf",
            content=b"archived",
            expected_checksum="0" * 64,
            checksum_algorithm="sha256",
        )

    client.error = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
    with pytest.raises(StorageWriteFailedError, match="could not be stored"):
        storage.put(
            key="document.pdf",
            content=b"archived",
            expected_checksum=calculate_checksum(b"archived"),
            checksum_algorithm="sha256",
        )


def test_s3_storage_maps_missing_and_unsafe_objects_to_support_safe_errors() -> None:
    client = FakeS3Client()
    storage = _storage(client)
    client.error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    with pytest.raises(StorageReadFailedError, match="not found"):
        storage.get(key="missing.pdf")
    with pytest.raises(StorageReadFailedError, match="unsafe storage key"):
        storage.get(key="../secret.pdf")


def test_s3_storage_maps_read_delete_and_malformed_response_failures() -> None:
    client = FakeS3Client()
    storage = _storage(client)
    client.error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")

    with pytest.raises(StorageReadFailedError, match="could not be read"):
        storage.get(key="document.pdf")
    with pytest.raises(StorageWriteFailedError, match="could not be deleted"):
        storage.delete(key="document.pdf")

    client.error = None
    client.get_response = {}
    with pytest.raises(StorageReadFailedError, match="could not be read"):
        storage.get(key="document.pdf")


def test_client_config_bounds_connect_read_and_retries() -> None:
    """Failure containment: a hung S3 endpoint must fail the request, never hold it."""
    from app.archive.s3_storage import client_config

    config = client_config(
        connect_timeout_seconds=2.5,
        read_timeout_seconds=11.0,
        max_attempts=4,
    )

    assert config.connect_timeout == 2.5
    assert config.read_timeout == 11.0
    assert config.retries == {"max_attempts": 4, "mode": "standard"}
