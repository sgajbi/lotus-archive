"""A duplicate key id is refused, not silently resolved (found reviewing #147).

`refuse_lifecycle_decision_against_bundle` resolved the signing key with

    published = {key.key_id: key for key in bundle.keys}

so a bundle carrying one id twice kept whichever entry came **last** and checked
the signature against that key's public bytes and window. Measured before
fixing: an operator listing the active signer in the retained set publishes two
`managed-v1` entries, and the verifier picks the retained one -- checking a
decision signed by the live key against a superseded public key, then reporting
`signature_invalid` for a genuine decision.

Two things make this worth a named refusal rather than a resolution rule:

  Every rule is wrong. Preferring the `active` entry trusts a bundle that is
  already malformed; preferring the `revoked` one silently changes which key the
  operator believes is in force.

  `lotus-idea`'s `ArchiveLifecycleTrustBundle.require_unique_key_ids` rejects the
  whole bundle on duplicate ids. Accepting it here made this reference
  implementation -- which exists to demonstrate what a consumer must do -- more
  permissive than the consumer.

Configuration is refused at startup as well, so the malformed bundle cannot be
published in the first place. Both halves are tested: a guard that only refuses
at read time leaves a bad document being served.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.archive.idea_lifecycle_decisions.models import (
    LifecycleKeyStatus,
    LifecycleVerificationKey,
    LifecycleVerificationKeys,
)
from app.archive.idea_lifecycle_decisions.signing import (
    LifecycleDecisionVerificationRefusal,
    refuse_lifecycle_decision_against_bundle,
)
from tests.unit.test_lifecycle_verification_keys import _decision, _signer


def _key(
    *,
    key_id: str,
    public_key_base64: str,
    status: LifecycleKeyStatus = LifecycleKeyStatus.ACTIVE,
    not_after_utc: datetime | None = None,
) -> LifecycleVerificationKey:
    return LifecycleVerificationKey(
        key_id=key_id,
        algorithm="ed25519",
        public_key_base64=public_key_base64,
        status=status,
        provenance="managed",
        not_before_utc=datetime(2025, 1, 1, tzinfo=UTC),
        not_after_utc=not_after_utc,
    )


def test_a_duplicate_key_id_is_refused_by_name() -> None:
    """The whole point: no verdict is trustworthy from a malformed document."""
    signer = _signer("managed-v1")
    bundle = LifecycleVerificationKeys(
        keys=[
            _key(key_id="managed-v1", public_key_base64="x" * 43),
            _key(
                key_id="managed-v1",
                public_key_base64="y" * 43,
                status=LifecycleKeyStatus.ROTATED,
                not_after_utc=datetime(2025, 6, 1, tzinfo=UTC),
            ),
        ]
    )

    refusal = refuse_lifecycle_decision_against_bundle(_decision(signer), bundle=bundle)

    assert refusal is LifecycleDecisionVerificationRefusal.KEY_ID_NOT_UNIQUE


def test_the_refusal_does_not_depend_on_which_entry_comes_first() -> None:
    """Order-independence is the property the dict comprehension lacked.

    It kept the last entry, so the verdict changed with the order of a list the
    caller does not control. Both orderings must now give the same answer.
    """
    signer = _signer("managed-v1")
    active = _key(key_id="managed-v1", public_key_base64="x" * 43)
    rotated = _key(
        key_id="managed-v1",
        public_key_base64="y" * 43,
        status=LifecycleKeyStatus.ROTATED,
        not_after_utc=datetime(2025, 6, 1, tzinfo=UTC),
    )

    for keys in ([active, rotated], [rotated, active]):
        assert (
            refuse_lifecycle_decision_against_bundle(
                _decision(signer), bundle=LifecycleVerificationKeys(keys=keys)
            )
            is LifecycleDecisionVerificationRefusal.KEY_ID_NOT_UNIQUE
        )


def test_a_duplicate_of_an_unrelated_key_does_not_refuse_this_decision() -> None:
    """Scoped to the id under test, not to the bundle as a whole.

    A malformed entry for some other key says nothing about whether *this*
    signature verifies, and refusing every decision because an unrelated pair
    collided would be a denial of service disguised as strictness.
    """
    signer = _signer("managed-v1")
    published = _published_for(signer)
    bundle = LifecycleVerificationKeys(
        keys=[
            *published,
            _key(key_id="managed-other", public_key_base64="a" * 43),
            _key(key_id="managed-other", public_key_base64="b" * 43),
        ]
    )

    assert refuse_lifecycle_decision_against_bundle(_decision(signer), bundle=bundle) is None


def test_a_unique_bundle_is_unaffected() -> None:
    """The control. Without it a verifier that refused everything would pass."""
    signer = _signer("managed-v1")
    bundle = LifecycleVerificationKeys(keys=_published_for(signer))

    assert refuse_lifecycle_decision_against_bundle(_decision(signer), bundle=bundle) is None


def _published_for(signer: object) -> list[LifecycleVerificationKey]:
    from base64 import urlsafe_b64encode

    raw = signer.private_key.public_key().public_bytes_raw()  # type: ignore[attr-defined]
    return [
        _key(
            key_id="managed-v1",
            public_key_base64=urlsafe_b64encode(raw).decode("ascii"),
        )
    ]


def test_configuration_refuses_a_retained_key_that_collides_with_the_signer() -> None:
    """Refused at startup, so the malformed bundle is never published.

    A read-time refusal alone would leave the service serving a document
    `lotus-idea` rejects outright, and the operator would learn about it from a
    consumer rather than from their own boot.
    """
    import json

    from tests.unit.test_archive_runtime import _production_settings
    from app.archive.exceptions import RuntimeConfigurationError

    with pytest.raises(RuntimeConfigurationError, match="must not also appear"):
        _production_settings(
            idea_lifecycle_decision_retained_verification_keys=json.dumps(
                [
                    {
                        "key_id": "managed-v1",
                        "public_key_base64": "y" * 43,
                        "not_before_utc": "2025-01-01T00:00:00+00:00",
                        "not_after_utc": "2025-06-01T00:00:00+00:00",
                    }
                ]
            ),
        )


def test_configuration_refuses_two_retained_keys_sharing_an_id() -> None:
    """The other way to publish a duplicate, which the signer check misses."""
    import json

    from tests.unit.test_archive_runtime import _production_settings
    from app.archive.exceptions import RuntimeConfigurationError

    entry = {
        "key_id": "managed-v0",
        "public_key_base64": "y" * 43,
        "not_before_utc": "2025-01-01T00:00:00+00:00",
        "not_after_utc": "2025-06-01T00:00:00+00:00",
    }
    with pytest.raises(RuntimeConfigurationError, match="must be unique"):
        _production_settings(
            idea_lifecycle_decision_retained_verification_keys=json.dumps([entry, dict(entry)]),
        )
