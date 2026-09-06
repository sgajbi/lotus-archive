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

from app.archive.idea_lifecycle_decisions.models import (
    IdeaLifecycleDecision,
    LifecycleVerificationKey,
)
from app.archive.idea_lifecycle_decisions.signing import (
    Ed25519LifecycleDecisionSigner,
    RetiredVerificationKey,
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


def _published_keys(
    signer: Ed25519LifecycleDecisionSigner,
    *,
    not_before_utc: datetime | None = None,
    retired: tuple[RetiredVerificationKey, ...] = (),
) -> list[LifecycleVerificationKey]:
    """Call the real published surface with only what it reads.

    Naming the three attributes in one place rather than inline: the previous
    stand-in duck-typed `_signer` alone and broke as soon as the method read
    another field, which tells you nothing about the behaviour under test.
    """
    from app.archive.idea_lifecycle_decisions.service import IdeaLifecycleDecisionService

    stand_in = type(
        "ServiceStandIn",
        (),
        {
            "_signer": signer,
            "_signing_key_not_before_utc": not_before_utc,
            "_retired_verification_keys": retired,
        },
    )()
    return IdeaLifecycleDecisionService.verification_keys(stand_in)


def _trust_store_from(
    published: list[LifecycleVerificationKey],
) -> dict[str, Ed25519PublicKey]:
    """Build the consumer's trusted-key mapping the way a consumer would.

    From the published document only -- no access to any signer -- because that
    is the whole claim the distribution route makes.
    """
    return {
        key.key_id: Ed25519PublicKey.from_public_bytes(urlsafe_b64decode(key.public_key_base64))
        for key in published
    }


def test_ephemeral_provenance_is_distinguishable() -> None:
    """A consumer must be able to refuse a development key.

    An ephemeral key is regenerated per process, so a decision signed under it
    cannot be verified after a restart. Trusting one in a production store
    silently accepts unverifiable evidence, which is why provenance is a field
    rather than something inferred from the key_id by each consumer.
    """
    ephemeral = _published_keys(_signer("ephemeral-local-v1"))
    managed = _published_keys(_signer("managed-v1"))

    assert ephemeral[0].provenance == "ephemeral_development"
    assert managed[0].provenance == "managed"


def test_a_decision_still_verifies_after_the_signer_rotates() -> None:
    """The point of retention, and what a list alone did not deliver.

    A decision signed under key n, verified from the document published after
    the service has rotated to n+1. Before retention this failed: the published
    document carried the active signer only, so key n vanished and every
    decision it signed became unverifiable to anyone building trust from it.
    """
    outgoing = _signer("managed-v1")
    decision = _decision(outgoing)

    rotated_at = datetime.now(UTC)
    incoming = _signer("managed-v2")
    published = _published_keys(
        incoming,
        not_before_utc=rotated_at,
        retired=(
            RetiredVerificationKey(
                key_id=outgoing.key_id,
                public_key_base64=outgoing.public_key_base64(),
                not_before_utc=rotated_at - timedelta(days=90),
                not_after_utc=rotated_at,
            ),
        ),
    )

    assert [key.key_id for key in published] == ["managed-v2", "managed-v1"]
    assert verify_lifecycle_decision(decision, trusted_keys=_trust_store_from(published))


def test_rotation_without_retention_loses_the_old_decision() -> None:
    """The negative control that makes the test above mean something.

    Publishing only the new signer -- exactly what this service did before --
    leaves the old decision unverifiable. Without this, the test above would
    pass for any trust store that happened to contain the right key.
    """
    outgoing = _signer("managed-v1")
    decision = _decision(outgoing)

    published = _published_keys(_signer("managed-v2"), not_before_utc=datetime.now(UTC))

    assert [key.key_id for key in published] == ["managed-v2"]
    assert not verify_lifecycle_decision(decision, trusted_keys=_trust_store_from(published))


def test_every_published_key_carries_the_window_a_consumer_selects_by() -> None:
    """A consumer picks a key by the decision's issue time.

    A key published without a window cannot be selected correctly for a
    historical decision, so the window is part of the contract rather than
    documentation. The active key's end is open; a retired key's is closed,
    because a retired key trusted without an end never stops being accepted.
    """
    rotated_at = datetime.now(UTC)
    published = _published_keys(
        _signer("managed-v2"),
        not_before_utc=rotated_at,
        retired=(
            RetiredVerificationKey(
                key_id="managed-v1",
                public_key_base64=_signer("managed-v1").public_key_base64(),
                not_before_utc=rotated_at - timedelta(days=90),
                not_after_utc=rotated_at,
            ),
        ),
    )

    active, retired = published
    assert active.status == "active"
    assert active.not_before_utc == rotated_at
    assert active.not_after_utc is None

    assert retired.status == "retired"
    assert retired.not_after_utc == rotated_at
    assert retired.not_before_utc < retired.not_after_utc
