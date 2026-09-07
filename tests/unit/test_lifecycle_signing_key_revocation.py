"""A revoked key must stop signing, not only be published as revoked (#147).

Publishing the status while continuing to sign with the key would tell every
consumer to reject exactly the decisions this service is still minting -- a
service issuing evidence it has itself declared worthless.

Against the real `IdeaLifecycleDecisionService`, not a stand-in, because the
claim spans two surfaces that a stand-in cannot exercise together: `issue`
refusing, and `verification_keys` still publishing the key so consumers can act
on the withdrawal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.authorization import ArchiveAuthorizationPolicy
from app.archive.idea_lifecycle_decisions.models import LifecycleKeyStatus
from app.archive.idea_lifecycle_decisions.repository import (
    SqliteIdeaLifecycleDecisionRepository,
)
from app.archive.idea_lifecycle_decisions.service import (
    IdeaLifecycleDecisionService,
    LifecycleDecisionSigningKeyRevokedError,
)
from app.archive.idea_lifecycle_decisions.signing import Ed25519LifecycleDecisionSigner
from app.archive.service import ArchiveDocumentService
from tests.unit.test_idea_lifecycle_decision_service import (
    PRIVATE_KEY,
    _archive,
    _idea_context,
    _request,
)

SIGNING_KEY_ID = "archive-local-v1"


def test_a_revoked_signing_key_refuses_to_issue(tmp_path: Path) -> None:
    """The service stops minting decisions it has declared unverifiable."""
    archive, document_id, audit = _archive(tmp_path)
    service = _service(tmp_path, archive, audit, revoked=frozenset({SIGNING_KEY_ID}))

    with pytest.raises(LifecycleDecisionSigningKeyRevokedError):
        service.issue(
            document_id=document_id,
            request=_request(),
            idempotency_key="idem-revoked-1",
            caller_context=_idea_context(),
            trace_id="trace-revoked-1",
        )


def test_the_same_call_succeeds_when_the_key_is_not_revoked(tmp_path: Path) -> None:
    """The control. Without it, a service broken in any way would pass above."""
    archive, document_id, audit = _archive(tmp_path)
    service = _service(tmp_path, archive, audit, revoked=frozenset())

    decision = service.issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="idem-ok-1",
        caller_context=_idea_context(),
        trace_id="trace-ok-1",
    )

    assert decision.signing_key_id == SIGNING_KEY_ID


def test_revocation_also_refuses_an_idempotent_replay(tmp_path: Path) -> None:
    """The case a check placed later would miss.

    A decision issued before the revocation is already in the ledger, and
    `issue` serves a repeat of the same idempotency key from there. If the
    revocation check sat after that lookup, a replay would hand back a decision
    signed by the withdrawn key -- freshly, on request, after revocation.

    So the same key is replayed across two services: one before the key was
    revoked, one after.
    """
    archive, document_id, audit = _archive(tmp_path)
    before = _service(tmp_path, archive, audit, revoked=frozenset())
    issued = before.issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="idem-replay-1",
        caller_context=_idea_context(),
        trace_id="trace-replay-1",
    )
    assert issued.signing_key_id == SIGNING_KEY_ID

    after = _service(tmp_path, archive, audit, revoked=frozenset({SIGNING_KEY_ID}))

    with pytest.raises(LifecycleDecisionSigningKeyRevokedError):
        after.issue(
            document_id=document_id,
            request=_request(),
            idempotency_key="idem-replay-1",
            caller_context=_idea_context(),
            trace_id="trace-replay-2",
        )


def test_a_revoked_signer_still_publishes_its_key_as_revoked(tmp_path: Path) -> None:
    """Refusing to sign is half of it; the withdrawal must also be observable.

    If the service stopped signing *and* dropped the key, a consumer holding
    decisions it already accepted would have no way to learn they are withdrawn.
    """
    archive, _, audit = _archive(tmp_path)
    service = _service(tmp_path, archive, audit, revoked=frozenset({SIGNING_KEY_ID}))

    (key,) = service.verification_keys()

    assert key.key_id == SIGNING_KEY_ID
    assert key.status is LifecycleKeyStatus.REVOKED


def _service(
    tmp_path: Path,
    archive: ArchiveDocumentService,
    audit: InMemoryAccessAuditRepository,
    *,
    revoked: frozenset[str],
) -> IdeaLifecycleDecisionService:
    return IdeaLifecycleDecisionService(
        posture_reader=archive,
        repository=SqliteIdeaLifecycleDecisionRepository(tmp_path / "decisions.sqlite3"),
        signer=Ed25519LifecycleDecisionSigner(
            private_key=PRIVATE_KEY,
            key_id=SIGNING_KEY_ID,
        ),
        authorization_policy=ArchiveAuthorizationPolicy(),
        audit_repository=audit,
        signing_key_not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        revoked_key_ids=revoked,
    )
