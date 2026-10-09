# Pooled result custody acceptance

[Issue #188](https://github.com/sgajbi/lotus-archive/issues/188) includes a bounded
same-family v5 admission addendum for [Report #431](https://github.com/sgajbi/lotus-report/issues/431).
Archive retains the exact pooled result selector and opaque Report revision digests;
Performance owns the financial result and Report owns source admission/projection.
V5 adds no calculator, approval ledger, endpoint or report family.

## Contract and qualification

`composite_review.v5` retains the existing seven-field identity envelope with
`EXPLICIT_RETAINED_CALCULATED_REPLAY` and `NOT_ATTESTED`. The strict selector pins
tenant/composite, calculation UUID, source schema/metric/method, positive interval,
currency, fee view/basis, policy binding/content, day-count/fallback policy, engine,
source manifest, input/bundle/response digests, exact member population and source
vector. Source pins retain owner/product/version/revision/cut, payload digest,
compatibility group, coverage and complete unique page identities/count.
Correction UUID and predecessor response digest are both required nullable fields:
both null values mean original; both populated mean a distinct source predecessor.
Archive never derives a financial revision or reconstructs predecessor economics.

The selector schema is pinned to Report candidate
`de686fd67e3582934c851cd371e28c7c8c68d88d`. Raw owner checkout schema SHA-256
`b9e8033b3637bc8799acfba972346f007aa1c31ff042e8b875b38dfdbcf8974d`
and committed LF schema SHA-256
`d067fd9b356a882c0ea24b4c9ba2738f7f179883bc0e7afd4c76f950ed0944ce`
are distinct byte pins with exact decoded JSON equality, not interchangeable hashes.
The checked-in selector schema equals the Archive model schema exactly.

The seven retained identity examples originate in actual registered Report worker
packages, producer manifest SHA-256
`67a5da54d746051b5318cf8d856f804b4e8d3daa05cd3418e2e5aff0ee4cd87f`.
Archive intake `16c4f3` exit 0 verified all 56 artifacts. These cover original and
corrected `AVAILABLE`, four `NOT_CALCULABLE` outcomes and elected
`FALLBACK_ANALYSIS`. The identity pins those whole responses; numerical outcomes
remain in Report's dataset/workbook, not in a second Archive financial model.
Neither unavailable result nor fallback becomes zero, bank attestation or automatic
XIRR success. Archive cannot infer outcomes from opaque digests.

Report subsequently qualified the same production contract on main
`4af947726dab91adec94b098fa9985d5bd6f15f6`, natural run `37960050194`
with all nine checks successful. The immutable candidate package receipt is
preserved; producer main qualification does not imply joined Archive acceptance.

## Custody and upgrade

The existing direct selection join requires exact enclosing tenant/composite/
period/as-of and matched `composite-review/v5` XLSX axes. Render remains the only
create authority. Full identity, Report revision and bytes participate in immutable
replay. Existing metadata/download/source-events/retention/audit/current and explicit
document correction routes retain historical originals. Source calculation
predecessors and Archive document relationships are separate identities; Archive
does not manufacture a relationship from a source calculation UUID.

Apply pending migration018 after017 through the owning deployment procedure.
`018_add_composite_pooled_custody.sql` extends only the existing scope CHECK with
v5 axes/qualification/selector bounds and paired correction pins. It adds no
table/column and rewrites no retained record/object. Typed API models own complete
nested strictness. Historical014–017 remain unchanged; never replay their older
guards over retained v5. Keep compatible readers/schema and forward-fix.

Component proof uses the actual seven source identities with explicitly synthetic
OOXML transport; it is not an actual Render workbook. Tests cover exact identities,
schema equality, invalid fields/digests/metric/method, missing correction pins,
self-correction, duplicate population/source/page vectors, enclosing scope,
immutable valid mutation conflicts, tenant denial, retries, full bytes, source
events, retention, audit and explicit original→technical→corrected document chains.
The populated PostgreSQL test retains eleven v1–v4 documents, proves old guard
refusal before upgrade, retains eight v5 documents, rejects corrupt SQL insert/update
atomically, refuses unsafe historical guard replay and reopens all nineteen in
separate processes. Required hosted database execution is distinct from local tests.

From the Archive root, with an explicitly isolated test database configured in
`LOTUS_ARCHIVE_TEST_DATABASE_URL` (the test truncates its data), Windows:

```powershell
$env:LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF='1'
.venv/Scripts/python.exe -m pytest tests/integration/test_postgres_composite_pooled_upgrade.py
```

Linux/macOS, from the Archive root:

```bash
LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1 .venv/bin/python -m pytest tests/integration/test_postgres_composite_pooled_upgrade.py
```

## Remaining acceptance

The source package evidence uses recorded Performance transport, registered Report
ASGI intake/native worker and SQLite with a declining Render503 boundary. It does
not prove a live Performance principal, Report PostgreSQL, actual v5 workbook or
Archive handoff. Protected candidate/main qualification and wiki publication are
recorded in the issue evidence. A later actual joined R8 campaign requires a qualified
cohort and explicit owned native resource lease; no R7 runtime or sealed packet is
reused. V4 genuine monthly amendment, pooled joined acceptance, institutional
IAM/source authority/capacity/recovery, Report #417 and programme #923 remain open.
