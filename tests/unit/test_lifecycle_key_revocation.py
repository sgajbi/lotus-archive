"""Revocation is a published status a verifier reads, not a deletion (#147).

`LifecycleVerificationKey.status` was published on every key and read by
nothing. Measured against the shipped verifier, `active`, `revoked`,
`compromised` and `definitely-not-valid` all produced the same verdict, because
`refuse_lifecycle_decision_against_bundle` never looked at the field. #143 found
the identical defect one layer along -- a declared validity window with no
reader -- and fixing that instance was not evidence the class was gone from the
same document.

Two things separate this from the window checks that already existed:

  **Revocation is not retirement.** A rotated key keeps verifying decisions
  inside its closed window; that is what retention is for. A revoked key
  verifies at no instant, including inside the window it genuinely signed in,
  because what is being withdrawn is the claim that its signatures ever carried
  Archive's authority.

  **Revocation is not removal.** The previous guidance said to withdraw a
  compromised key by deleting it from the published document. That answers
  "this key was never Archive's" for a key that was -- destroying the very
  distinction #143 built the refusal vocabulary to preserve.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.archive.idea_lifecycle_decisions.models import (
    LifecycleKeyStatus,
    LifecycleVerificationKey,
    LifecycleVerificationKeys,
)
from app.archive.idea_lifecycle_decisions.signing import (
    LifecycleDecisionVerificationRefusal,
    RetainedVerificationKey,
    refuse_lifecycle_decision_against_bundle,
)
from tests.unit.test_lifecycle_verification_keys import (
    _decision,
    _published_keys,
    _signer,
)

VOCABULARY = (
    Path(__file__).resolve().parents[1] / "fixtures" / "lifecycle_key_status_vocabulary.json"
)


def test_the_published_vocabulary_is_the_governed_one() -> None:
    """The enum matches the governed vocabulary, checked against a file.

    Against a vendored copy of the contract rather than a list retyped into
    this test: a hand-written list is a second opinion about the vocabulary,
    and two opinions cannot disagree usefully because both live here.

    Being exact about what this does and does not prove. Archive's CI has no
    `lotus-platform` checkout, so this cannot detect drift on the platform side
    -- it proves the code matches the copy Archive took, and the fixture
    records the source blob SHA so a human or a cross-repo sweep can re-verify
    that the copy is still faithful. Claiming more would be the false green
    this repository has been bitten by before.
    """
    governed = json.loads(VOCABULARY.read_text(encoding="utf-8"))["status"]

    assert [status.value for status in LifecycleKeyStatus] == governed


def test_the_removed_vocabulary_can_no_longer_be_published() -> None:
    """`retired` is refused, which is what proves the rename actually took.

    Renaming the emitted value while the type still accepted the old one would
    leave both publishable, and every existing test would keep passing.
    """
    with pytest.raises(ValidationError):
        _key(status="retired")


@pytest.mark.parametrize("status", ["", "compromised", "definitely-not-valid", "ACTIVE"])
def test_an_unknown_status_cannot_be_constructed(status: str) -> None:
    """The field was an unconstrained `str`, so all four of these were publishable.

    An empty string is in the list deliberately: it is the value a missing
    configuration produces, and it was indistinguishable from a real status.
    """
    with pytest.raises(ValidationError):
        _key(status=status)


def test_a_revoked_key_is_refused_inside_the_window_it_really_signed_in() -> None:
    """The load-bearing case.

    The decision is genuine: signed by that key, inside its own validity
    window, with an intact signature. Every check that existed before passes.
    It is refused anyway, and refused *as revoked*, because a revoked key's
    past signatures are exactly what revocation withdraws.

    Refusing only outside the window would be the existing retirement check
    passing under a new name.
    """
    signer = _signer("managed-v1")
    signed_at = datetime.now(UTC) - timedelta(minutes=1)
    bundle = LifecycleVerificationKeys(
        keys=_published_keys(
            signer,
            not_before_utc=signed_at - timedelta(days=30),
            revoked=frozenset({"managed-v1"}),
        )
    )

    refusal = refuse_lifecycle_decision_against_bundle(
        _decision(signer, issued_at=signed_at), bundle=bundle
    )

    assert refusal is LifecycleDecisionVerificationRefusal.KEY_REVOKED


def test_the_same_decision_verifies_when_the_key_is_not_revoked() -> None:
    """The control that makes the test above mean something.

    Same signer, same instant, same window, same signature -- only `status`
    differs. Without this, a bug that refused everything would pass.
    """
    signer = _signer("managed-v1")
    signed_at = datetime.now(UTC) - timedelta(minutes=1)
    bundle = LifecycleVerificationKeys(
        keys=_published_keys(signer, not_before_utc=signed_at - timedelta(days=30))
    )

    assert (
        refuse_lifecycle_decision_against_bundle(
            _decision(signer, issued_at=signed_at), bundle=bundle
        )
        is None
    )


def test_revocation_is_reported_differently_from_deletion() -> None:
    """Why removal is not the mechanism, stated as a difference in the verdict.

    The same compromised key, withdrawn two ways. Marking it revoked says "this
    was ours and its signatures are withdrawn". Deleting it says "this was never
    ours" -- an ordinary trust-distribution miss, and the wrong thing to hand an
    operator investigating a compromise.
    """
    signer = _signer("managed-v1")
    signed_at = datetime.now(UTC) - timedelta(minutes=1)
    not_before = signed_at - timedelta(days=30)
    decision = _decision(signer, issued_at=signed_at)

    revoked = LifecycleVerificationKeys(
        keys=_published_keys(signer, not_before_utc=not_before, revoked=frozenset({"managed-v1"}))
    )
    deleted = LifecycleVerificationKeys(
        keys=_published_keys(_signer("managed-v2"), not_before_utc=not_before)
    )

    assert (
        refuse_lifecycle_decision_against_bundle(decision, bundle=revoked)
        is LifecycleDecisionVerificationRefusal.KEY_REVOKED
    )
    assert (
        refuse_lifecycle_decision_against_bundle(decision, bundle=deleted)
        is LifecycleDecisionVerificationRefusal.KEY_NOT_PUBLISHED
    )


def test_rotation_is_unaffected_by_the_status_check() -> None:
    """A rotated key still verifies inside its closed window.

    The regression this change could plausibly cause: reading `status` and
    refusing anything that is not `active` would break retention entirely, and
    the revocation tests above would not notice.
    """
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    rotated_at = datetime.now(UTC)
    bundle = LifecycleVerificationKeys(
        keys=_published_keys(
            incoming,
            not_before_utc=rotated_at,
            retained=(
                RetainedVerificationKey(
                    key_id="managed-v1",
                    public_key_base64=_public_key_of(outgoing),
                    not_before_utc=rotated_at - timedelta(days=30),
                    not_after_utc=rotated_at,
                ),
            ),
        )
    )

    inside = _decision(outgoing, issued_at=rotated_at - timedelta(minutes=1))
    after = _decision(outgoing, issued_at=rotated_at + timedelta(minutes=1))

    assert refuse_lifecycle_decision_against_bundle(inside, bundle=bundle) is None
    assert (
        refuse_lifecycle_decision_against_bundle(after, bundle=bundle)
        is LifecycleDecisionVerificationRefusal.KEY_ALREADY_ROTATED
    ), "a late decision is still late, not revoked"


def test_a_rotated_key_that_is_also_revoked_reports_the_revocation() -> None:
    """Both facts are true; the verifier must report the more severe one.

    A key that rotated out and was *later* found to be compromised is the
    ordinary case. Answering `KEY_ALREADY_ROTATED` for a decision outside its
    window would be technically true and would hide the compromise.
    """
    outgoing, incoming = _signer("managed-v1"), _signer("managed-v2")
    rotated_at = datetime.now(UTC)
    bundle = LifecycleVerificationKeys(
        keys=_published_keys(
            incoming,
            not_before_utc=rotated_at,
            retained=(
                RetainedVerificationKey(
                    key_id="managed-v1",
                    public_key_base64=_public_key_of(outgoing),
                    not_before_utc=rotated_at - timedelta(days=30),
                    not_after_utc=rotated_at,
                ),
            ),
            revoked=frozenset({"managed-v1"}),
        )
    )

    for issued_at in (rotated_at - timedelta(minutes=1), rotated_at + timedelta(minutes=1)):
        assert (
            refuse_lifecycle_decision_against_bundle(
                _decision(outgoing, issued_at=issued_at), bundle=bundle
            )
            is LifecycleDecisionVerificationRefusal.KEY_REVOKED
        )


def test_a_revoked_signing_key_is_still_published() -> None:
    """Withdrawal must be observable, so the key stays in the document.

    An unpublished revocation is not a revocation: this bundle is the only
    place a consumer can learn that the signatures it already accepted are
    withdrawn.
    """
    published = _published_keys(
        _signer("managed-v1"),
        not_before_utc=datetime.now(UTC) - timedelta(days=1),
        revoked=frozenset({"managed-v1"}),
    )

    (key,) = published
    assert key.key_id == "managed-v1"
    assert key.status is LifecycleKeyStatus.REVOKED


def _key(*, status: str) -> LifecycleVerificationKey:
    return LifecycleVerificationKey(
        key_id="managed-v1",
        algorithm="ed25519",
        public_key_base64="x" * 43,
        status=status,  # type: ignore[arg-type]
        not_before_utc=datetime.now(UTC),
        provenance="managed",
    )


def _public_key_of(signer: object) -> str:
    from base64 import urlsafe_b64encode

    raw = signer.private_key.public_key().public_bytes_raw()  # type: ignore[attr-defined]
    return urlsafe_b64encode(raw).decode("ascii")
