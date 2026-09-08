from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.archive.idea_lifecycle_decisions.models import (
    IdeaLifecycleDecision,
    LifecycleKeyStatus,
    LifecycleVerificationKeys,
)


@dataclass(frozen=True)
class RetainedVerificationKey:
    """A key that no longer signs but must stay published.

    Its window is closed by definition: rotation is what makes `not_after_utc`
    knowable, and a rotated key trusted without an end never stops being
    accepted.

    Held as provisioned metadata rather than derived, because the private key is
    gone by the time a key rotates out -- the public half and the window it
    signed in are all that remain, and both have to be carried forward
    deliberately.

    Named for retention rather than for a status, because a retained key may be
    published as `rotated` or as `revoked`. Revocation is expressed separately,
    by key id, since it also applies to the key that is still signing.
    """

    key_id: str
    public_key_base64: str
    not_before_utc: datetime
    not_after_utc: datetime

    def __post_init__(self) -> None:
        if not self.key_id or not self.public_key_base64:
            raise ValueError("a retained verification key needs an id and a public key")
        # Built with **entry from parsed JSON, so these arrive as strings and
        # the annotations above would otherwise be a claim nothing enforces.
        # Comparing them as strings gives right answers for well-formed UTC
        # values and wrong ones across offsets, which is the worst combination:
        # it passes the tests written to check it.
        object.__setattr__(self, "not_before_utc", _as_datetime(self.not_before_utc))
        object.__setattr__(self, "not_after_utc", _as_datetime(self.not_after_utc))


def _as_datetime(value: datetime | str) -> datetime:
    """An aware UTC datetime, from configuration that may carry either form."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("a verification key window instant must carry a timezone")
    return parsed.astimezone(UTC)


class LifecycleDecisionSigner(Protocol):
    @property
    def key_id(self) -> str: ...

    def sign(self, payload: Mapping[str, object]) -> tuple[str, str]: ...

    def public_key_base64(self) -> str:
        """The verification key for `key_id`, base64url, no padding stripped.

        Published so a consumer can populate `verify_lifecycle_decision`'s
        `trusted_keys`. Derived from the signing key itself rather than from
        configuration, so a published key cannot disagree with the key that
        signed.
        """


@dataclass(frozen=True)
class Ed25519LifecycleDecisionSigner:
    private_key: Ed25519PrivateKey
    key_id: str

    def sign(self, payload: Mapping[str, object]) -> tuple[str, str]:
        canonical = _canonical_payload(payload)
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        signature = "ed25519:" + urlsafe_b64encode(self.private_key.sign(canonical)).decode("ascii")
        return digest, signature

    def public_key_base64(self) -> str:
        raw = self.private_key.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        return urlsafe_b64encode(raw).decode("ascii")


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


class LifecycleDecisionVerificationRefusal(str, Enum):
    """Why a decision was not accepted, so a consumer can act on the reason.

    A bare `False` cannot distinguish "this key was never ours" from "this key
    was ours and had rotated out before this decision claims to have been
    issued" -- the second is evidence of a forged or back-dated decision, the
    first is an ordinary trust-distribution miss.

    `KEY_ID_NOT_UNIQUE` is not a property of the decision at all -- it says the
    published document is malformed, so no verdict about this signature can be
    trusted. It is separated from `KEY_NOT_PUBLISHED` because "we cannot answer"
    and "this key was never ours" send an operator to different places.

    `KEY_REVOKED` is a third answer again, and the reason it cannot collapse
    into either: the key was ours, the decision falls inside the window it
    genuinely signed in, and it is still refused. Reporting that as
    `KEY_NOT_PUBLISHED` would describe a withdrawn key as one Archive never
    held; reporting it as `KEY_ALREADY_ROTATED` would say the signature was
    fine but late. Both would be untrue, and an operator acting on either would
    look in the wrong place.
    """

    KEY_NOT_PUBLISHED = "key_not_published"
    KEY_ID_NOT_UNIQUE = "key_id_not_unique"
    KEY_REVOKED = "key_revoked"
    KEY_NOT_YET_VALID = "key_not_yet_valid"
    KEY_ALREADY_ROTATED = "key_already_rotated"
    KEY_IS_EPHEMERAL = "key_is_ephemeral"
    SIGNATURE_INVALID = "signature_invalid"


def refuse_lifecycle_decision_against_bundle(
    decision: IdeaLifecycleDecision,
    *,
    bundle: LifecycleVerificationKeys,
    at_utc: datetime | None = None,
) -> LifecycleDecisionVerificationRefusal | None:
    """`None` when the decision verifies against the published bundle.

    The reference implementation of what a consumer must do with
    `GET /documents/idea-lifecycle-decisions/verification-keys`, which Archive
    publishes and, until now, did not itself consume.

    `verify_lifecycle_decision` takes a plain `key_id -> public key` mapping.
    That resolves the key and checks the signature, and it structurally cannot
    enforce the validity windows this service publishes beside each key --
    Archive declared a window and shipped no code that reads one. A consumer
    building `trusted_keys` from the bundle and dropping the windows would
    accept a decision claiming to be issued years after the key that signed it
    rotated out, which is precisely what retention makes possible and what the
    window exists to bound.

    Selection is by the decision's `issued_at_utc`, not by wall clock: the
    question is whether this key was the signing key when the decision says it
    was issued. Using "now" would make every historical decision unverifiable
    the moment its key rotated out, which is the failure retention removed.
    """

    matching = [key for key in bundle.keys if key.key_id == decision.signing_key_id]
    if not matching:
        return LifecycleDecisionVerificationRefusal.KEY_NOT_PUBLISHED
    if len(matching) > 1:
        # A dict comprehension keyed by `key_id` silently kept the last entry,
        # so a bundle publishing one id twice -- an operator listing the active
        # signer in the retained set, say -- resolved to whichever came last and
        # checked the signature against the wrong public key. It reported
        # `signature_invalid` for a genuine decision, or a window verdict from
        # the wrong key's dates.
        #
        # Refused rather than resolved by a rule, because every rule here is
        # wrong: preferring the active entry trusts a bundle that is already
        # malformed, and preferring the revoked one silently changes which key
        # the operator thinks is in force. lotus-idea's consumer contract
        # rejects the whole bundle on duplicate ids, so accepting it here made
        # this reference implementation more permissive than the consumer it
        # exists to demonstrate.
        return LifecycleDecisionVerificationRefusal.KEY_ID_NOT_UNIQUE
    key = matching[0]

    if key.status is LifecycleKeyStatus.REVOKED:
        # Deliberately ahead of both window checks. Revocation withdraws the
        # signatures the key already made, so it has to refuse *inside* the
        # window the key genuinely signed in -- a check placed after the window
        # comparisons would only ever fire where the existing ones already did,
        # and would pass its test while changing nothing.
        return LifecycleDecisionVerificationRefusal.KEY_REVOKED

    if key.provenance != "managed":
        # Regenerated per process, so a decision signed under it cannot be
        # verified after a restart. Accepting one would make a local
        # development key indistinguishable from provisioned custody.
        return LifecycleDecisionVerificationRefusal.KEY_IS_EPHEMERAL

    issued_at = decision.issued_at_utc
    if issued_at < key.not_before_utc:
        return LifecycleDecisionVerificationRefusal.KEY_NOT_YET_VALID
    if key.not_after_utc is not None and issued_at >= key.not_after_utc:
        # Half-open on purpose: a rotation sets the outgoing key's
        # `not_after_utc` to the incoming key's `not_before_utc`, so a closed
        # upper bound would make both keys valid at that instant and neither
        # answer wrong.
        return LifecycleDecisionVerificationRefusal.KEY_ALREADY_ROTATED

    public_key = Ed25519PublicKey.from_public_bytes(
        urlsafe_b64decode(key.public_key_base64.encode("ascii"))
    )
    if not verify_lifecycle_decision(
        decision, trusted_keys={key.key_id: public_key}, at_utc=at_utc
    ):
        return LifecycleDecisionVerificationRefusal.SIGNATURE_INVALID
    return None
