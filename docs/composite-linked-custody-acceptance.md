# Linked-analysis custody acceptance

Issue [#185](https://github.com/sgajbi/lotus-archive/issues/185) adds strict
`composite_review.v3` to the existing XLSX document, immutable retry, source-event,
retention and correction paths. Component and populated PostgreSQL proof are
complete locally. Qualified joined Report→Render→Archive HTTP acceptance remains
pending; v1/v2 acceptance under #176/#182 remains completed.

## Contract and authority

The [custody contract](composite-custody-contract.md#v3-linked-analysis) defines
the exact linked selection. Report owns lifecycle IDs and the series, source
revision and factual digests. Performance owns linked financial facts and source
authority. Render owns actual XLSX output and transmit provenance. Archive owns
measured bytes, retained metadata, access audit and document lifecycle evidence.

The historical reviewed Report r3 44-file contract manifest is
`c03c79ce3d9a99d09027d33d5525a779b6a6e639d34c8cea5ec0ea222f18d386`.
Its historical custody schema SHA-256 is
`f400ea8b9f4e76bcbfeeb96e95f547070d7bbec8a673c125880bb6c486848877`.
The separately accepted 56-file current Performance original/corrected source
manifest is `d397d25d1884940fe2cbfdeb363d74083a8221c73d49b9da18c72d326c78b391`.
Neither packet is an actual Report job/render/Archive submission. The latter must
come from Report's existing lifecycle after changed mains qualify.

The successor Report r4 candidate manifest is
`036a775cdc0ac6dcc1533211fa80b6a9d6f2413f2397be2a931cbf9cb17a6c72`
(33 sealed files, rehashed by Archive native `d1e5db` exit 0). Its custody schema
SHA-256 is `578001c3ef24964694382bacacbdcc05b71a0c2233106f395665a74336b02870`.
It supplies actual original/corrected Report job, snapshot, revision and custody
contexts, plus an exact retained-original package rebuild. It adds optional
null-only request `restatement_sequence` and correct uncaptured-null reason
semantics without changing financial values. It is candidate Report lifecycle
proof with controlled capability and Render-503 boundary, not a qualified joined
mainline Render/Archive execution or an archived technical rerender.

Member source authority remains in Report source/snapshot and source-bearing
content, bound by the exact opaque custody digests and job/snapshot/revision.
No raw financial facts store, calculator, second custody ledger, report family,
distributed transaction or financial publication authority is added.
Calculated replay remains `EXPLICIT_RETAINED_CALCULATED_REPLAY` / `NOT_ATTESTED`;
the supplier environment is `CONTROLLED_SYNTHETIC_ONLY`.

## Executable component example

`tests/fixtures/composite_linked.py` preserves actual r4 Report lifecycle/source
context in `composite_linked_original.json` and `composite_linked_corrected.json`,
with explicitly synthetic Archive/Render transport and OOXML bytes. The separate
9-key model fixture uses r3 draft selection and digest sentinels solely to test
absent-field compatibility. None is actual joined mainline HTTP custody.
`tests/integration/test_composite_linked_custody.py` submits the registered API,
checks exact identity/bytes, idempotent retries, changed identity/content 409,
cross-tenant 403, source events, audit, retention, correction retry and current
resolution. The retained original remains unchanged after correction.

From the Archive repository root on Windows:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_composite_linked_identity.py tests/integration/test_composite_linked_custody.py tests/e2e/test_composite_linked_custody_journey.py
```

On Linux/macOS:

```bash
.venv/bin/python -m pytest tests/unit/test_composite_linked_identity.py tests/integration/test_composite_linked_custody.py tests/e2e/test_composite_linked_custody_journey.py
```

## Populated PostgreSQL upgrade and recovery

Apply only pending migration 016 after 014+015 through the owning deployment
procedure. This repository exposes migration gates, not an operated production
migration runner. Keep compatible schema/readers and forward-fix; never replay
014/015 over retained v3 or delete objects/identity to make rollback pass.

The destructive test below requires an explicitly isolated test database supplied
in `LOTUS_ARCHIVE_TEST_DATABASE_URL`; never point it at shared or production data.
From the Archive root on Windows:

```powershell
$env:LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF='1'
.venv/Scripts/python.exe -m pytest tests/integration/test_postgres_composite_linked_upgrade.py
```

On Linux/macOS:

```bash
LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1 .venv/bin/python -m pytest tests/integration/test_postgres_composite_linked_upgrade.py
```

It populates v1 and v2 original/correction rows under real 014+015, proves the old
guard refuses v3, applies/reapplies 016 and compares every retained SQL row.
It admits v3 original/correction, rejects corrupt insert/update and mixed axes,
then proves unsafe historical replay fails atomically with all five records and
the compatible catalog constraint unchanged. A separate process reopens the same
filesystem/database, checks full content, all three identity versions, retries,
source events and both corrected-current chains. Backup, restore, runtime HTTP
restart and enterprise qualification remain distinct evidence requirements.

## Delivery evidence and remaining acceptance

Local native evidence: baseline valid-v3 refusal `b24d99` exit 1; restored focused
v1/v2/v3 proof `61a640` exit 0; deliberately disabled vector validator `1b6429`
exit 1 caused six intended negative-test failures. The validator was restored
before subsequent gates. Populated PostgreSQL proof `c8945e` exit 0 and full
required-PostgreSQL integration `2a57c8` exit 0 (153 passed) succeeded. Static
type/OpenAPI/migration/code-health gates `193177` exit 0 succeeded.

Current r4-fixture proof: `c3c62b` exit 0 (594 unit passed, 47 optional proofs
skipped), `0f5a3a` exit 0 (153 required-PostgreSQL integration passed), and
`cada81` exit 0 (10 required-PostgreSQL end-to-end passed). Bare combined coverage
gate `fd3430` exit 0 measured 99.45%, including 100% of the new linked module.
Static/type/schema/migration/code-health completion `2dc4d8` exit 0 and final lint
`7c9780` exit 0 passed. Integration `21f4db` exit 1 correctly refused reused
synthetic v2 workbook bytes under a different r4 document reference; distinct
explicitly synthetic v3 content corrected the fixture before the passing rerun.
No production collision guard was relaxed.

The optional-null refinement is represented as two strict typed request shapes:
nine required fields with sequence absent, or those fields plus required null.
Both input and output schemas preserve strict source fields. Actual r4 original
and corrected identities round-trip exactly; absence versus null conflicts on
an existing immutable request. Non-null competing sequences refuse in the model
and PostgreSQL guard. All enclosing Archive requirements remain in force.

Wiki source check `973b46` exit 0 reports two expected authored page changes.
Wiki quality audit `bcb7c6` exit 1 remains a failed advisory audit for unchanged
technical OS-temp prose in Architecture.md:85 and Configuration.md:25/84/104/178.
Base and current blobs are respectively `470ccf9bbf4de5ef7efd75cc76ef735e3d2568cf`
and `455ee3dede8bd0fe886fa811c72b3fe8957f3099`, unchanged (`442277` exit 0).
The authoritative wiki skill explicitly says to preserve an OS "temporary
directory" technical term. Changed API-Surface/Operations pages pass its
presentation checks; this classification does not turn the failed audit green or
waive a required check. Root owns the central auditor follow-up. No other repo
or unrelated wiki page was changed.
The README already links the custody contract, so no README change is needed.

Signed PR, required checks, exact-main release, wiki publication/parity and actual
qualified joined HTTP custody are pending. Public evidence must be posted and
read back before bounded closure. Full Report #417/programme #923, institutional
supplier/bank authority, wider product acceptance, nonfunctional qualification
and actual restore certification remain open.

The manual checkout, wiki-source junction and seven earlier recovery refs remain
retained after automatic approval review rejected their removal with only
`blocked by policy`. No retry or workaround is authorized by this delivery.
