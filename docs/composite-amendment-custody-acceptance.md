# Monthly amendment custody

Archive admits Report's `composite_review.v6` identity through the existing Composite
XLSX family. The qualification is `CONTROLLED_MONTHLY_SOURCE_AMENDMENT_REPLAY` and
publication remains `NOT_ATTESTED`. Archive retains identity and bytes; Manage owns
eligibility/amendment facts and Report owns the selection, projection and lifecycle
digests. Custody grants no checker, financial, source or client-publication authority.

## Contract and compatibility

The strict selector is Report's existing `eligibility_selection` with required
`selection_version=v2`. Source product v2 is independent of definition product v1/v2.
Both `PUBLISHED` and `EVALUATED_ONLY` retain one to thirty-one ordered receipt pins
per selected month. Each pin retains product version, evaluation revision, approval
content hash, receipt content hash and response digest. Published pins additionally
require `parent_publication_response_digest`. All fields are required and unknown
fields are refused. Full nested receipts/source facts remain in Report's retained
snapshot and source-bearing artifact; Archive retains the exact selector pins and
opaque Report digests without reconstructing the source workflow.

The consumed frozen Report handoff has JSON SHA-256
`904d0d2cfcc9403ad4e44530cf496475a3fe84fdd5648c1d129bbb4206aae194` and ZIP
`52389e32326c0b5359e24367dfb49032277c94478fd84821b8e395de7c4e7a28`.
Eleven listed entries match their individual hashes. An additional request schema
is covered by the whole ZIP hash. The four definition/evidence-kind examples are
controlled Manage545 in-memory fixtures, not actual native packet exports.
`tests/fixtures/composite_amendment_selection.schema.json` is the exact selector
and referenced DTO closure from that immutable schema, compared structurally with
the Archive model. Existing v1-v5 schemas are unchanged; no older identity is
implicitly promoted to v6 and absent `selection_version` cannot enter v6.

Existing scope joins, immutable metadata replay, PostgreSQL JSON persistence,
metadata/download/source-events/retention/current-document APIs and lifecycle
relationships retain the whole typed identity. Changed valid receipt vectors,
ordering, definition or parent publication pins conflict under an existing request.
Technical rerender retains identical source identity; an Archive `/correct` edge
alone does not establish a genuine Manage monthly amendment.

## Migration and recovery boundary

Apply pending `019_add_composite_amendment_custody.sql` after018 before new admissions.
It replaces only the existing scope CHECK with version-matched v6 qualification,
selector and bounded lineage axes. No row, object, column, table or old migration
is rewritten. Keep a v6-compatible reader and constraint for retained v6 records.
Disable new admissions and forward-fix defects; never replay014–018 over retained
v6 or drop identity/objects to force rollback.

The required PostgreSQL test seeds nineteen v1-v5 documents before019, checks
pre-upgrade v6 refusal and unchanged rows after idempotent upgrade, then admits
twelve v6 component documents across both definition versions/evidence kinds.
Raw invalid SQL and unsafe historical migration replay must refuse atomically.
Fresh processes read all thirty-one records with exact identity, lineage, current
relationships and bytes. A fresh reader is component persistence proof; it is not
an actual database dump/restore or disaster recovery certification. Backup and
restore must retain the compatible schema, metadata, lifecycle/audit/hold rows and
objects together; actual joined v6 restore remains a separate issue188 criterion.

## Validation

From the Archive repository root, use its configured virtual environment.
On Windows:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_composite_amendment_identity.py tests/integration/test_composite_amendment_custody.py tests/e2e/test_composite_amendment_flow.py
make check
```

On Linux/macOS:

```bash
.venv/bin/python -m pytest tests/unit/test_composite_amendment_identity.py tests/integration/test_composite_amendment_custody.py tests/e2e/test_composite_amendment_flow.py
make check
```

Required hosted PostgreSQL proof uses an isolated test database and
`LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1`. From the same root on Windows:

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_postgres_composite_amendment_upgrade.py
```

On Linux/macOS:

```bash
.venv/bin/python -m pytest tests/integration/test_postgres_composite_amendment_upgrade.py
```

The supplied `LOTUS_ARCHIVE_TEST_DATABASE_URL` must name a disposable test database:
these tests truncate test rows and replay migrations. An absent local database
skip is not PostgreSQL evidence. Governed CI requires the database proof.

## Evidence posture

| Boundary | Meaning |
| --- | --- |
| Frozen handoff | Exact source-contract compatibility; controlled in-memory source examples. |
| API/filesystem component | Synthetic OOXML and explicitly synthetic opaque Report identity digests. |
| Required PostgreSQL | Populated forward upgrade, raw refusal, retained rows and separate-process reads. |
| Actual joined v6 | Pending qualified Report/Render/Archive native delivery and source packet export. Report remains JSON-only until receiver support. |
| Institutional acceptance | Source/checker authority, IAM, capacity, operated recovery and bank attestation remain separate. |

Issue188, Report417 and programme923 remain OPEN. No runtime split, financial
engine, source evaluator, endpoint, report family, ledger or new dependency is added.
