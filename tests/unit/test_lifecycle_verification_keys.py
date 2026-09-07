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
    IdeaLifecycleAction,
    IdeaLifecycleDecision,
    LifecycleVerificationKey,
    LifecycleVerificationKeys,
)
from app.archive.idea_lifecycle_decisions.signing import (
    Ed25519LifecycleDecisionSigner,
    LifecycleDecisionVerificationRefusal,
    RetiredVerificationKey,
    refuse_lifecycle_decision_against_bundle,
    verify_lifecycle_decision,
)

pytestmark = pytest.mark.governance


def _signer(key_id: str = "managed-v1") -> Ed25519LifecycleDecisionSigner:
    return Ed25519LifecycleDecisionSigner(private_key=Ed25519PrivateKey.generate(), key_id=key_id)


def _published_public_key(signer: Ed25519LifecycleDecisionSigner) -> Ed25519PublicKey:
    """Rebuild the key exactly as a consumer would, from the published string."""
    return Ed25519PublicKey.from_public_bytes(urlsafe_b64decode(signer.public_key_base64()))


def _decision(
    signer: Ed25519LifecycleDecisionSigner,
    *,
    issued_at: datetime | None = None,
    decision_id: str = "dec-1",
) -> IdeaLifecycleDecision:
    """A decision built from the REAL model and signed the way the service signs.

    Every field comes from `IdeaLifecycleDecision` rather than a convenient
    subset: a fixture that diverges from the real contract can make a broken
    verifier look correct, which is the failure this whole test file is
    guarding against.
    """
    issued = issued_at or datetime.now(UTC)
    payload = {
        "contract_version": "lotus-archive:IdeaEvidenceLifecycleDecision:v1",
        "decision_id": decision_id,
        "document_id": "doc-1",
        "idea_evidence_pack_id": "pack-1",
        "idea_candidate_id": "cand-1",
        "source_correlation_ref": "src-1",
        "tenant_id": "tenant-1",
        "residency_region": "SG",
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


# --------------------------------------------------------------------------
# Enforcement: the tests above prove the windows are PUBLISHED. These prove
# they are USED.
#
# Archive shipped `not_before_utc` and `not_after_utc` on every published key
# and no code that read one. `verify_lifecycle_decision` takes a plain
# `key_id -> public key` mapping -- `_trust_store_from` above builds exactly
# that, which is what a consumer does with this document -- and there is no
# parameter through which a window could reach it. So the windows were a
# contract nothing enforced, on the one route that exists to be consumed by
# somebody else.
# --------------------------------------------------------------------------


def _rotated_bundle(
    outgoing: Ed25519LifecycleDecisionSigner,
    incoming: Ed25519LifecycleDecisionSigner,
    rotated_at: datetime,
) -> LifecycleVerificationKeys:
    """The document published immediately after a rotation, from the real surface."""
    return LifecycleVerificationKeys(
        keys=_published_keys(
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
    )


def test_a_decision_from_either_side_of_the_rotation_verifies() -> None:
    """The handoff is an overlap, not a cutover.

    One document, one moment, both decisions accepted -- without the consumer
    being told which side of the rotation it is on.
    """
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)

    before = _decision(outgoing, issued_at=rotated_at - timedelta(minutes=1), decision_id="dec-old")
    after = _decision(incoming, issued_at=rotated_at + timedelta(minutes=1), decision_id="dec-new")

    assert refuse_lifecycle_decision_against_bundle(before, bundle=bundle) is None
    assert refuse_lifecycle_decision_against_bundle(after, bundle=bundle) is None


def test_a_decision_dated_after_its_key_retired_is_refused() -> None:
    """Retention is what makes this forgeable, and the window is what bounds it.

    The outgoing key stays published so decisions it really signed keep
    verifying. That same key must not vouch for a decision claiming to have
    been issued after it stopped signing.
    """
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)

    after_retirement = _decision(outgoing, issued_at=rotated_at + timedelta(minutes=1))

    assert (
        refuse_lifecycle_decision_against_bundle(after_retirement, bundle=bundle)
        is LifecycleDecisionVerificationRefusal.KEY_ALREADY_RETIRED
    )


def test_the_plain_trusted_keys_helper_cannot_enforce_the_window() -> None:
    """The finding itself, kept as a test so it cannot quietly return.

    `_trust_store_from` is the obvious way to consume this document, and it is
    the shape every test above uses. Fed the same decision the test above
    refuses, it accepts -- because the helper it feeds has nowhere to put a
    window.

    Not a defect in `verify_lifecycle_decision`: it does exactly what its
    signature promises. The defect was publishing a window that no shipped code
    read, leaving the only obvious consumer unable to honour it.
    """
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)

    after_retirement = _decision(outgoing, issued_at=rotated_at + timedelta(minutes=1))

    assert verify_lifecycle_decision(
        after_retirement, trusted_keys=_trust_store_from(bundle.keys)
    ), "if this ever fails, the windows reached the plain helper and this test is obsolete"


def test_a_decision_back_dated_before_its_key_existed_is_refused() -> None:
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)

    too_early = _decision(outgoing, issued_at=rotated_at - timedelta(days=91))

    assert (
        refuse_lifecycle_decision_against_bundle(too_early, bundle=bundle)
        is LifecycleDecisionVerificationRefusal.KEY_NOT_YET_VALID
    )


def test_the_rotation_instant_belongs_to_the_incoming_key() -> None:
    """Half-open, so exactly one key answers at the boundary.

    A rotation sets the outgoing key's `not_after_utc` to the incoming key's
    `not_before_utc`. A closed upper bound would leave both keys valid at that
    instant with neither answer wrong -- ambiguity that surfaces once, in
    production, at the one instant nobody tested.
    """
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)

    assert (
        refuse_lifecycle_decision_against_bundle(
            _decision(incoming, issued_at=rotated_at), bundle=bundle
        )
        is None
    )
    assert (
        refuse_lifecycle_decision_against_bundle(
            _decision(outgoing, issued_at=rotated_at), bundle=bundle
        )
        is LifecycleDecisionVerificationRefusal.KEY_ALREADY_RETIRED
    )


def test_a_key_that_was_never_published_is_refused() -> None:
    rotated_at = datetime.now(UTC)
    bundle = _rotated_bundle(_signer("managed-v1"), _signer("managed-v2"), rotated_at)

    stranger = _signer("managed-somebody-elses")

    assert (
        refuse_lifecycle_decision_against_bundle(_decision(stranger), bundle=bundle)
        is LifecycleDecisionVerificationRefusal.KEY_NOT_PUBLISHED
    )


def test_withdrawing_a_key_differs_from_retiring_it() -> None:
    """Retirement and compromise are not the same operation.

    A retired key keeps verifying decisions inside its window -- that is why it
    is retained. A compromised key must stop verifying everything it ever
    signed, including decisions that verified yesterday, because its signature
    no longer evidences Archive's authority. The mechanism is removal from the
    published document, and the operator needs to know that merely retiring a
    compromised key leaves it trusted for its whole historical window.
    """
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)
    decision = _decision(outgoing, issued_at=rotated_at - timedelta(minutes=1))

    assert refuse_lifecycle_decision_against_bundle(decision, bundle=bundle) is None

    withdrawn = LifecycleVerificationKeys(keys=_published_keys(incoming, not_before_utc=rotated_at))

    assert (
        refuse_lifecycle_decision_against_bundle(decision, bundle=withdrawn)
        is LifecycleDecisionVerificationRefusal.KEY_NOT_PUBLISHED
    )


def test_an_ephemeral_key_is_refused_however_valid_its_window() -> None:
    """Provenance is enforced, not merely distinguishable.

    The earlier test proves a consumer *can* tell an ephemeral key apart. This
    proves the reference consumer *does* refuse one, inside a valid window and
    with a genuine signature.
    """
    signer = _signer("ephemeral-local-v1")
    bundle = LifecycleVerificationKeys(
        keys=_published_keys(signer, not_before_utc=datetime.now(UTC) - timedelta(minutes=1))
    )

    assert (
        refuse_lifecycle_decision_against_bundle(_decision(signer), bundle=bundle)
        is LifecycleDecisionVerificationRefusal.KEY_IS_EPHEMERAL
    )


def test_a_decision_survives_a_restart_only_under_provisioned_key_material() -> None:
    """What `provenance` is actually claiming, proven as a restart.

    A managed signer is rebuilt from provisioned material, so the document
    published after a restart carries the same public key and the earlier
    decision still verifies. An ephemeral signer generates fresh material, so
    the restarted process publishes a key that verifies nothing it signed
    before -- and the refusal names provenance rather than leaving a consumer
    to diagnose an invalid signature.
    """
    private_key = Ed25519PrivateKey.generate()
    before_restart = Ed25519LifecycleDecisionSigner(private_key=private_key, key_id="managed-v1")
    decision = _decision(before_restart)
    started_at = datetime.now(UTC) - timedelta(minutes=1)

    # Same provisioned material, new process.
    after_restart = Ed25519LifecycleDecisionSigner(private_key=private_key, key_id="managed-v1")
    managed = LifecycleVerificationKeys(
        keys=_published_keys(after_restart, not_before_utc=started_at)
    )

    assert refuse_lifecycle_decision_against_bundle(decision, bundle=managed) is None

    # A process that generates its own key cannot do this, which is the whole
    # reason the ephemeral refusal exists.
    regenerated = _signer("ephemeral-local-v1")
    ephemeral_decision = _decision(regenerated)
    restarted_ephemeral = LifecycleVerificationKeys(
        keys=_published_keys(_signer("ephemeral-local-v1"), not_before_utc=started_at)
    )

    assert (
        refuse_lifecycle_decision_against_bundle(ephemeral_decision, bundle=restarted_ephemeral)
        is LifecycleDecisionVerificationRefusal.KEY_IS_EPHEMERAL
    )


def test_a_tampered_decision_is_refused_inside_a_valid_window() -> None:
    """Window and provenance are preconditions, not substitutes for the signature.

    The tamper flips a retain into an executed disposal, which is the change
    that would matter: it authorises destroying evidence.
    """
    rotated_at = datetime.now(UTC)
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    bundle = _rotated_bundle(outgoing, incoming, rotated_at)

    tampered = _decision(outgoing, issued_at=rotated_at - timedelta(minutes=1)).model_copy(
        update={
            "lifecycle_action": IdeaLifecycleAction.DISPOSAL_EXECUTED,
            "disposal_authorized": True,
        }
    )

    assert (
        refuse_lifecycle_decision_against_bundle(tampered, bundle=bundle)
        is LifecycleDecisionVerificationRefusal.SIGNATURE_INVALID
    )
