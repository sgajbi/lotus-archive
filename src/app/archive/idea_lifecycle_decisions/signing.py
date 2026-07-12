from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.archive.idea_lifecycle_decisions.models import IdeaLifecycleDecision


class LifecycleDecisionSigner(Protocol):
    @property
    def key_id(self) -> str: ...

    def sign(self, payload: Mapping[str, object]) -> tuple[str, str]: ...


@dataclass(frozen=True)
class Ed25519LifecycleDecisionSigner:
    private_key: Ed25519PrivateKey
    key_id: str

    def sign(self, payload: Mapping[str, object]) -> tuple[str, str]:
        canonical = _canonical_payload(payload)
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        signature = "ed25519:" + urlsafe_b64encode(self.private_key.sign(canonical)).decode("ascii")
        return digest, signature


def verify_lifecycle_decision(
    decision: IdeaLifecycleDecision,
    *,
    trusted_keys: Mapping[str, Ed25519PublicKey],
    at_utc: datetime | None = None,
) -> bool:
    if (at_utc or datetime.now(UTC)) >= decision.expires_at_utc:
        return False
    public_key = trusted_keys.get(decision.signing_key_id)
    if public_key is None or not decision.signature.startswith("ed25519:"):
        return False
    payload = decision.model_dump(
        mode="json",
        exclude={"payload_digest", "signature"},
    )
    canonical = _canonical_payload(payload)
    digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if digest != decision.payload_digest:
        return False
    try:
        public_key.verify(
            urlsafe_b64decode(decision.signature.removeprefix("ed25519:")),
            canonical,
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def _canonical_payload(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
