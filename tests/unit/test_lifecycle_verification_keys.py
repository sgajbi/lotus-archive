"""The published verification key must actually verify a real decision.

Publishing a key that does not verify is worse than publishing none: a
consumer would build a trust store from it and reject every genuine decision,
with no signal pointing at the key as the cause.

So these tests take the key from the published surface and feed it to
`verify_lifecycle_decision` — the consumer's real entry point — rather than
asserting the endpoint returns a plausibly-shaped string.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.archive.idea_lifecycle_decisions.models import IdeaLifecycleDecision
from app.archive.idea_lifecycle_decisions.signing import (
    Ed25519LifecycleDecisionSigner,
    verify_lifecycle_decision,
)

pytestmark = pytest.mark.governance


def _signer(key_id: str = "managed-v1") -> Ed25519LifecycleDecisionSigner:
    return Ed25519LifecycleDecisionSigner(private_key=Ed25519PrivateKey.generate(), key_id=key_id)


def _published_public_key(signer: Ed25519LifecycleDecisionSigner) -> Ed25519PublicKey:
    """Rebuild the key exactly as a consumer would, from the published string."""
    return Ed25519PublicKey.from_public_bytes(urlsafe_b64decode(signer.public_key_base64()))


def _decision(signer: Ed25519LifecycleDecisionSigner) -> IdeaLifecycleDecision:
    """A decision built from the REAL model and signed the way the service signs.

    Every field comes from `IdeaLifecycleDecision` rather than a convenient
    subset: a fixture that diverges from the real contract can make a broken
    verifier look correct, which is the failure this whole test file is
    guarding against.
    """
    issued = datetime.now(UTC)
    payload = {
        "contract_version": "lotus-archive:IdeaEvidenceLifecycleDecision:v1",
        "decision_id": "dec-1",
        "document_id": "doc-1",
        "idea_evidence_pack_id": "pack-1",
        "idea_candidate_id": "cand-1",
        "source_correlation_ref": "src-1",
        "tenant_id": "tenant-1",
        "residency_region": "eu-west-1",
        "retention_policy_id": "policy-1",
        "legal_hold_status": "clear",
        "legal_hold_count": 0,
        "purge_status": "not_eligible",
        "lifecycle_action": "RETAIN",
        "disposal_authorized": False,
        "decision_reason_code": "retained_by_policy",
        "authority": "lotus-archive",
        "issued_at_utc": issued.isoformat(),
        "expires_at_utc": (issued + timedelta(minutes=5)).isoformat(),
        "correlation_id": "corr-1",
        "trace_id": "trace-1",
        "signing_algorithm": "Ed25519",
        "signing_key_id": signer.key_id,
    }
    # Sign exactly as IdeaLifecycleDecisionService.issue does: validate into the
    # model first, dump it in JSON mode excluding the signature fields, and sign
    # THAT. Signing the raw dict instead produces a different canonical form and
    # a signature the real verifier rejects -- which is precisely the fake-fidelity
    # trap this fixture would otherwise fall into.
    signable = IdeaLifecycleDecision.model_validate(
        {**payload, "payload_digest": "sha256:pending", "signature": "ed25519:pending"}
    ).model_dump(mode="json", exclude={"payload_digest", "signature"})
    digest, signature = signer.sign(signable)
    return IdeaLifecycleDecision.model_validate(
        {**payload, "payload_digest": digest, "signature": signature}
    )


def test_published_key_verifies_a_real_decision() -> None:
    """The whole point: a consumer holding only the published key can verify."""
    signer = _signer()
    decision = _decision(signer)

    assert verify_lifecycle_decision(
        decision, trusted_keys={signer.key_id: _published_public_key(signer)}
    )


def test_a_different_key_does_not_verify() -> None:
    """Negative control: verification must actually depend on the key material.

    Without this, a `verify` that returned True unconditionally would pass the
    test above.
    """
    signer = _signer()
    decision = _decision(signer)
    impostor = _signer()

    assert not verify_lifecycle_decision(
        decision, trusted_keys={signer.key_id: _published_public_key(impostor)}
    )


def test_an_unpublished_key_id_does_not_verify() -> None:
    """A decision whose key_id is absent from the trust store is refused.

    This is the fail-closed behaviour the distribution route exists to make
    usable: the consumer can only populate the store from published keys.
    """
    signer = _signer()
    decision = _decision(signer)

    assert not verify_lifecycle_decision(
        decision, trusted_keys={"some-other-key": _published_public_key(signer)}
    )


def test_published_key_matches_the_signing_key() -> None:
    """Derived from the signer, so a published key cannot disagree with it."""
    signer = _signer()
    published = _published_public_key(signer)

    assert published.public_bytes_raw() == signer.private_key.public_key().public_bytes_raw()


def test_ephemeral_provenance_is_distinguishable() -> None:
    """A consumer must be able to refuse a development key.

    An ephemeral key is regenerated per process, so a decision signed under it
    cannot be verified after a restart. Trusting one in a production store
    silently accepts unverifiable evidence, which is why provenance is a field
    rather than something inferred from the key_id by each consumer.
    """
    from app.archive.idea_lifecycle_decisions.service import IdeaLifecycleDecisionService

    ephemeral = IdeaLifecycleDecisionService.verification_keys(
        type("S", (), {"_signer": _signer("ephemeral-local-v1")})()
    )
    managed = IdeaLifecycleDecisionService.verification_keys(
        type("S", (), {"_signer": _signer("managed-v1")})()
    )

    assert ephemeral[0]["provenance"] == "ephemeral_development"
    assert managed[0]["provenance"] == "managed"
