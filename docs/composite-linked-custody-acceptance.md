# Linked-analysis custody acceptance

Issue [#185](https://github.com/sgajbi/lotus-archive/issues/185) adds strict
`composite_review.v3` to the existing XLSX document, immutable retry, source-event,
retention and correction paths. Component and populated PostgreSQL proof are
complete. Qualified joined Report→Render→Archive HTTP custody, actual restart,
isolated PostgreSQL/object restore and owned runtime retirement are proved below.
V1/v2 acceptance under #176/#182 remains completed. Calculated replay remains
controlled and `NOT_ATTESTED`.

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

## Component delivery evidence

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

## Actual joined v3 custody and recovery

The qualified source cohort used Archive
`f75adf60873b06ae4cea90fff8ebf4ac21cb5faa`, Report
`7fc0dbc6ce3a81fedb9bcf3d9b6e5ec22cd03648`, and Render
`535d0d5f87fd2f8bd701ba8707b343022060d030`. Archive implementation PR
[#186](https://github.com/sgajbi/lotus-archive/pull/186) has a verified signed
candidate and identical rebased-main tree; exact-main release run
`37917714507` passed all nine jobs. Published wiki commit
`0810ebb2aa968c1200b40f8d2de8f831434f0f1f` passed strict committed-blob parity.
The replacement source admission explicitly records corrected Render qualification;
historical startup cohort and leases remain preserved.

The actual 52-file producer manifest is
`25a991954fcaed28a76f82daace59471cc362855a84e4a9b4b4b26662009d2bb`.
Archive independently rehashed every file and bound each complete package to its
fresh Report snapshot payload, job, revision and three custody digests. Frozen r4
selection and source response remain the financial baseline; fresh opaque Report
lifecycle digests are bound to the actual snapshot rather than assumed unchanged.

| Label | Retained document | Meaning |
|---|---|---|
| O | `doc_b2da366ee2f6440bb9afa25996fe66bb` | Original calculated linked report |
| T | `doc_9395309ec8ba439a859218d09b351ad4` | Technical rerender from the retained original snapshot |
| C | `doc_411beb7906ac4775b51cd6edfdf89b91` | Financially corrected source result |

O and T retain the same Report job, snapshot, revision and custody identity, with
distinct Render jobs, document IDs and measured XLSX bytes. C has a distinct
Report lifecycle and financial custody identity. The existing lifecycle records
explicit `correct` edges O→T→C; every current lookup resolves C. Historical
metadata and complete downloads remain available unchanged.

Archive actual HTTP proof `3eb100` exit 0 verifies full retained metadata and
workbook bytes against the fresh packages and Render sender wires, source events,
retention and access audit. Exact retries return 201; changed source digest,
absent-versus-null sequence and changed content return 409. Foreign tenant
metadata, download, source-event and retention requests return 403. Root's
independent live reader `4dd41e` exit 0 accepted the joined chain; the public
[programme evidence](https://github.com/sgajbi/lotus-report/issues/417#issuecomment-6080034790)
records the bounded acceptance and its qualification limits.

Actual restart `7d5605` exit 0 opens the same owned PostgreSQL volume and original
filesystem objects at the same source revision, with a new HTTP process and no
migration replay. All four SQL tables, the compatible constraint and all three
objects match the pre-restart snapshot exactly. Fresh network HTTP proof
`0b7766` exit 0 compares complete metadata, source events, retention and downloads
to the live proof and verifies the final chain and tenant refusals again.

Actual isolated restore `4d6c9d` exit 0 restores a custom PostgreSQL dump into a
fresh database and copies the object root without overwriting either live store.
The 31,458-byte dump SHA-256 is
`8ee31bb921ea61b92aa38342229994c8c4160155de3ca9832f62f1caac835fee`;
its table-of-contents read succeeds. Full before/after-dump snapshots are equal:
three documents, 123 access-audit rows, two lifecycle relationships and no legal
holds. Every full SQL row and workbook hash/size matches the restored copy before
any restored API audit writes.

The initial strict printed-constraint comparison `f05ab9` exit 1 is preserved.
PostgreSQL reparses the dumped CHECK and removes redundant parentheses; all rows
and objects already matched. A transaction-local temporary table reparses the
original CHECK, then its complete PostgreSQL deparse exactly equals the restored
constraint. The temporary transaction is rolled back. Both expressions and this
proof are retained; substring matching does not qualify the guard.

A fresh registered API process reads the restored database and copied objects,
verifying all three custody identities, full downloads, source events, retention,
final current chain and tenant refusal. This is actual isolated PostgreSQL and
object recovery with registered API verification, separately from the original
network HTTP proof. It does not certify enterprise recovery, RTO or RPO.

Earlier failed process-generation string formatting and UTF-8 BOM launch attempts
are retained in the task evidence. They do not qualify a restart; the successful
source-bound generation and exact before/after proof do. No historical migration,
financial source recapture, shared service or original retained object was changed.

### Reader and transmitter examples

Report reads retained metadata and bytes; Render alone transmits artifacts.
Report's technical rerender uses the existing retained snapshot and records the
O→T correction. The controlled financial correction records T→C through the
same lifecycle API. Archive does not infer correction order from timestamps.
For an existing request, use `/documents/by-request-id/{archive_request_id}`;
historical document lookup and `/current` serve different reader needs.

The following read example uses the actual synthetic O identifier and caller
scope from the sealed HTTP packet. Run from any directory against a separately
authorized local runtime containing that packet; the delivery runtime is retired
after acceptance. These headers exercise local trusted-caller admission, not a
production identity provider.

Windows PowerShell:

```powershell
$archiveBaseUrl = 'http://127.0.0.1:55887'
$documentId = 'doc_b2da366ee2f6440bb9afa25996fe66bb'
$headers = @{'X-Caller-Service'='lotus-report'; 'X-Actor-Type'='service'; 'X-Actor-Id'='archive-custody-reader'; 'X-Tenant-Id'='synthetic-tenant-a'; 'X-Region'='APAC'; 'X-Correlation-Id'='linked-custody-reader'; 'X-Trace-Id'='linked-custody-reader'}
Invoke-RestMethod -Uri "$archiveBaseUrl/documents/$documentId" -Headers $headers
Invoke-RestMethod -Uri "$archiveBaseUrl/documents/$documentId/current" -Headers $headers
Invoke-WebRequest -Uri "$archiveBaseUrl/documents/$documentId/download" -Headers $headers -OutFile './retained-original.xlsx'
Get-FileHash -LiteralPath './retained-original.xlsx' -Algorithm SHA256
```

Linux/macOS Bash:

```bash
archive_base_url=http://127.0.0.1:55887
document_id=doc_b2da366ee2f6440bb9afa25996fe66bb
headers=(-H 'X-Caller-Service: lotus-report' -H 'X-Actor-Type: service' -H 'X-Actor-Id: archive-custody-reader' -H 'X-Tenant-Id: synthetic-tenant-a' -H 'X-Region: APAC' -H 'X-Correlation-Id: linked-custody-reader' -H 'X-Trace-Id: linked-custody-reader')
curl --fail-with-body "${headers[@]}" "$archive_base_url/documents/$document_id"
curl --fail-with-body "${headers[@]}" "$archive_base_url/documents/$document_id/current"
curl --fail-with-body "${headers[@]}" "$archive_base_url/documents/$document_id/download" -o ./retained-original.xlsx
```

Compare the full downloaded byte count and SHA-256 to the metadata response;
the sealed original hash is
`4becf3da6d37f11aac6c103c7589f374be04eec153ea1d5a0b203e3d2082ee25`.
The same supported paths were invoked by `3eb100` and `0b7766`, including full
byte comparison and the persisted tenant/region boundary. The current response
identifies C while the historical O response retains its original identity.

Root independent post-restart/restore review `f6f8eb` exit 0 accepted actual
original/restored PostgreSQL rows, audit prefixes, object bytes and the parsed
guard. Retirement `ce47f9` exit 0 rechecked the exact owned process generations,
source, container and volume, then proved those processes, the container, named
volume and ports absent. Final original and restored custom dumps, readable TOCs,
and full before/after snapshots are retained; the backup manifest is
`2b6612ca37bc082161ab95819710e7d969929884ef94049d4f6fb41eac41fbe4`.
Original and copied object roots remain identical. The final 103-file evidence
manifest is `26e19c103f86400f26adef3c83ca7c843897a99070fa065bf3064fd9a522aced`
(native `11fc5a` exit 0). Earlier sealed R2–R5 evidence remains unchanged.
Bounded issue closure requires this documentation on validated main, authored
wiki publication/parity and public final evidence posted and read back.
Calculated replay remains controlled synthetic, uses local trusted caller
headers, and is `NOT_ATTESTED`. Report #417/programme #923, institutional source
and bank authority, production authentication, enterprise scale and broader
nonfunctional qualification remain open. The separately reproduced wiki-auditor
false positive is tracked in
[lotus-platform #943](https://github.com/sgajbi/lotus-platform/issues/943);
the original advisory audit remains failed.

The manual checkout, wiki-source junction and seven earlier recovery refs remain
retained after automatic approval review rejected their removal with only
`blocked by policy`. No retry or workaround is authorized by this delivery.
