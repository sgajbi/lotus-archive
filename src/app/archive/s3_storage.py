from __future__ import annotations

from base64 import b64encode
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.archive.checksum import calculate_checksum
from app.archive.exceptions import (
    DocumentChecksumMismatchError,
    StorageReadFailedError,
    StorageWriteFailedError,
)
from app.archive.storage import StoredObject


class ReadableBody(Protocol):
    def read(self) -> bytes: ...


class S3Client(Protocol):
    def head_bucket(self, **kwargs: object) -> Mapping[str, object]: ...

    def put_object(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_object(self, **kwargs: object) -> Mapping[str, object]: ...

    def delete_object(self, **kwargs: object) -> Mapping[str, object]: ...


class S3ObjectStorage:
    provider = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        namespace: str,
        key_prefix: str,
        region: str | None,
        endpoint_url: str | None,
        server_side_encryption: str,
        kms_key_id: str | None,
        client: S3Client | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("S3 bucket must not be blank")
        self.bucket = bucket
        self.namespace = namespace
        self._key_prefix = key_prefix.strip("/")
        self._server_side_encryption = server_side_encryption
        self._kms_key_id = kms_key_id
        self._client = client or cast(
            S3Client,
            boto3.client("s3", region_name=region, endpoint_url=endpoint_url),
        )

    def check_ready(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("archive_storage_unavailable") from exc

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

        request: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": self._object_key(key),
            "Body": content,
            "ContentLength": len(content),
            "ChecksumSHA256": b64encode(bytes.fromhex(actual_checksum)).decode("ascii"),
            "ServerSideEncryption": self._server_side_encryption,
            "Metadata": {
                "checksum-algorithm": checksum_algorithm,
                "checksum": actual_checksum,
            },
        }
        if self._server_side_encryption == "aws:kms":
            request["SSEKMSKeyId"] = self._kms_key_id
        try:
            self._client.put_object(**request)
        except (BotoCoreError, ClientError) as exc:
            raise StorageWriteFailedError("archive object could not be stored") from exc

        return StoredObject(
            provider=self.provider,
            namespace=self.namespace,
            key=key,
            checksum_algorithm=checksum_algorithm,
            checksum=actual_checksum,
            size_bytes=len(content),
        )

    def get(self, *, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=self._object_key(key))
            body = cast(ReadableBody, response["Body"])
            return body.read()
        except ClientError as exc:
            error = cast(Mapping[str, object], exc.response.get("Error", {}))
            if str(error.get("Code", "")) in {"404", "NoSuchKey", "NotFound"}:
                raise StorageReadFailedError("stored document object was not found") from exc
            raise StorageReadFailedError("archive object could not be read") from exc
        except (BotoCoreError, KeyError, TypeError) as exc:
            raise StorageReadFailedError("archive object could not be read") from exc

    def delete(self, *, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._object_key(key))
        except (BotoCoreError, ClientError) as exc:
            raise StorageWriteFailedError("archive object could not be deleted") from exc

    def _object_key(self, key: str) -> str:
        path = PurePosixPath(key)
        if path.is_absolute() or ".." in path.parts:
            raise StorageReadFailedError("unsafe storage key")
        return "/".join(part for part in (self._key_prefix, key.lstrip("/")) if part)
