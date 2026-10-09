# Eligibility evidence custody acceptance

[Issue #188](https://github.com/sgajbi/lotus-archive/issues/188) extends the existing
Composite XLSX custody path with Report-owned `composite_review.v4`. Its strict
selection retains Manage eligibility evidence rather than inventing a Performance
calculation. Component admission, populated PostgreSQL upgrade and the bounded R7
Report→Render→Archive custody campaign have passed. R7 used registered Report ASGI
intake and actual TCP Manage capture, Render submission and Archive custody.
It does not prove network ingress into Report or institutional deployment.
Completed v1/v2/v3 custody and their sealed evidence remain unchanged.

## Source and authority

The current Report-owned r3 interface freeze has receipt SHA-256
`031da9119fc7efdc794fc4056b16e72f7dbb04900df611d1e66a22ef5490d48b`.
Its dataset schema SHA-256 is
`2214d2044980fc81007637e0504a46d13b2cbf10959fd2ca2198d2ed5f557e73`;
the strict selection schema is
`cd71b7ab72fc9fd5493ca399e3a1f53690b426b8d652628e0b70a40c54f53171`;
the interface matrix is
`348259b5add5a3a8bec679a1b6036c5ac80285392156e534df30cd0f7b9559aa`.
Archive intake `b2ac95` exit 0 verifies all three byte counts and hashes; both
schemas are byte-identical to r2. R3 distinguishes the observation/evaluation cut
from the parent universe cut. Archive retains their separate exact pins and
opaque digests; it does not assert equality across distinct source cuts.
The freeze establishes the output wire, not signed source authority.

Manage owns source eligibility proposals, publication receipts, canonical
membership, universe and history. Report owns capture, complete report projection
and job/snapshot/revision digests. Render owns the actual workbook and transmit
provenance. Archive retains the exact selection, opaque verified Report digest
values and measured workbook bytes through existing custody controls.
Archive does not evaluate eligibility rules, reconstruct approval, recalculate
money or introduce a source facts store, approval ledger or distributed transaction.

Qualification is `CONTROLLED_ELIGIBILITY_SOURCE_REPLAY`; publication remains
`NOT_ATTESTED`. `PUBLISHED` identifies available source publication evidence;
it does not attest bank approval, official activation or genuine source authority.
`EVALUATED_ONLY` retains a proposal and explicitly has no publication, approval
or canonical history pins. Source remains controlled and unverified.

## Exact identity and scope

The custody identity keeps the existing seven-field envelope: contract version,
qualification, publication state, selection, series digest, source-revision digest
and factual-content digest. The three Report digests are bare lowercase 64-hex;
source pins use the exact `sha256:` spelling.

The selection has tenant, composite, definition version, reporting currency,
complete-month horizon and 1–120 ordered unique monthly pins. Explicit selected
month gaps are permitted by the producer and remain gaps; Archive never fills
them with invented evidence. The first and last selected months match the horizon.
No calculation ID, linked request, return-view methodology or financial window
vector belongs in this selection.

Each `PUBLISHED` month retains evaluation revision, proposal/approval/receipt
content hashes, whole receipt response digest, membership revision/content/response,
attestation version, universe content/response, parent membership revision/content/
response, positive strict publication sequence, publication response digest and
source cut. Each `EVALUATED_ONLY` month retains evaluation revision, proposal
content/response, parent membership revision/content and source cut. The strict
discriminator refuses relabeling, missing required pins, unexpected approval
fields, unknown fields and invalid hash spellings.

The existing Archive scope validator already joins tenant/composite/horizon/as-of
and exact template/data-contract/XLSX axes for this direct selection shape.
There is no enclosing Archive currency field: the exact selected currency is
retained and changes conflict on immutable replay. Report independently binds
that currency to its complete source responses and snapshot.

The r2 projection correction distinguishes known zero reason occurrences
(`NOT_APPLICABLE` / `NO_APPLICABLE_REASONS`) and rule-defined unused numeric slots
(`NOT_APPLICABLE` / `RULE_FIELD_NOT_APPLICABLE`) from genuinely unavailable source
values. Report/Render validate the complete eight-table projection against full
source months. Archive's create API receives metadata and workbook bytes, not
the Report dataset; it preserves exact custody and does not manufacture a
parallel source projection. R7 binds the full fresh Report snapshot/package and
actual Render bytes to the retained Archive identity.

## Upgrade and recovery boundary

Apply pending `017_add_composite_eligibility_custody.sql` after 016 through the
owning deployment procedure. Migration 016 explicitly restricts v1/v2/v3 and
calculated qualification; JSON column reuse alone cannot admit v4. Migration 017
replaces only the existing bounded scope CHECK, admitting the v4 qualification,
direct selection, complete-month horizon and bounded evidence-kind vector. It
adds no column/table and rewrites no retained row or object. Full nested schema
strictness remains the typed API model's responsibility.

Historical migrations 014/015/016 remain unchanged. Never replay them over retained
v4. Disable new admissions and keep the compatible reader/schema when forward-fixing.
The populated upgrade test retains v1 plus original/correction pairs for v2/v3,
then v4 original/technical/corrected triples for both evidence kinds. It compares
all eleven SQL records, proves unsafe historical guard replay refuses atomically,
rejects corrupt insert/update and reopens identities, complete bytes, retries,
source events, retention and corrected-current chains in a separate process.
This is separate from actual network restart, backup/restore and enterprise recovery.

The test below requires an explicitly isolated database in
`LOTUS_ARCHIVE_TEST_DATABASE_URL`; it truncates its test data. From the Archive root
on Windows:

```powershell
$env:LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF='1'
.venv/Scripts/python.exe -m pytest tests/integration/test_postgres_composite_eligibility_upgrade.py
```

Linux/macOS, from the Archive root:

```bash
LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1 .venv/bin/python -m pytest tests/integration/test_postgres_composite_eligibility_upgrade.py
```

## Component and mainline proof

The checked-in schema fixture exactly equals the frozen Report selector schema.
Synthetic fixture IDs, source hashes and OOXML transport are explicitly component
values, not actual Manage or joined producer evidence. Unit tests cover both
modes, unknown/missing pins, month ordering/duplicates/horizon, explicit gaps,
120/121 capacity, publication promotion and strict publication sequences.
Registered API tests cover full identity/download preservation, immutable
digest/source-pin/currency/revision/content conflicts, Render-only transmission,
cross-tenant reads and explicit original→technical→corrected relationships.

Meaningful RED `64ff00` exit 1 proves both valid v4 kinds were refused by the old
union. Focused legacy/v4 proof `9260f1` exit 0 passes 125 tests; expanded v4 unit
and consumer proof `b9d362` exit 0 passes 41 tests. API `3ba83c` exit 1 initially
refused a synthetic fixture's incorrect region, then `66db36` exit 0 passed all
nine after correcting fixture scope; no authorization guard was relaxed.

Implementation [PR #189](https://github.com/sgajbi/lotus-archive/pull/189) merged
at `75b84ee8760f615693ca11e12eb99e376e080939`. Its protected run `37936730102`
passed all seven checks, including required real PostgreSQL execution; natural
main run `37937237633` passed all nine. Authored wiki publication `0e9bf67`
matched all ten committed source blobs. Native static/unit proof passed 634 tests
with 48 declared skips; affected API/E2E proof passed 40 with five database-only
skips covered by the required hosted PostgreSQL lane.

## Actual R7 custody and recovery

The controlled cohort pinned Archive `75b84ee`, Render `68b8d39`, Report
`0e658df` and Manage `566d32f`. Each fresh definition example captured 32 actual
Manage TCP reads before any Render/Archive submission. Original raw capture
inputs and their hashes were retained separately from decoded-equal serialized
convenience copies; no pin was reconstructed or relaxed.

Four actual Report XLSX jobs produced eight archived workbooks: an original and
one retained technical rerender for each definition/evidence combination.
Definition v1 and v2 are distinct examples, not an original/corrected source pair.
The following retained IDs are evidence examples, not reusable production inputs.

| Definition / evidence | Original document | Retained technical document |
| --- | --- | --- |
| v1 / evaluated-only | `doc_595fb9d61cde4a0994d94cfea910ac6f` | `doc_d405a3412db64e998b2246131c7a1e9b` |
| v1 / published | `doc_24fec3a768ee4679ade5272e5786bed1` | `doc_d9ccf0b523c547b1947655169ad71f1f` |
| v2 / evaluated-only | `doc_4ce20a3cfad140c8a51d1964c18a92af` | `doc_a8e8b808910c464d9339590d86567e43` |
| v2 / published | `doc_162907ac9c28464f87ac0703bcd536c8` | `doc_a3cfd176ff5d4287a03518d4dc4c2508` |

For each document, Archive proof `9803a7` exit 0 joins the actual Report job,
snapshot, revision, full Render package, sender metadata and strict identity.
It compares full producer/download/object bytes, size and SHA-256; exact retained
replay returns 201, valid changed digest/pin/currency/bytes return 409, Report
creation returns 403, and five foreign-tenant read routes return 403. Existing
source-event, retention, audit and current-document routes preserve the identity.
Native Report technical rerender uses Archive's `/correct` relationship and
`correction_of_document_id`; unchanged source identity makes this technical
lineage, not a genuine monthly financial amendment or a `/reissue` execution.

Independent reader `90e289` exit 0 checked all eight XLSX files and 2,212 canonical
and display cells against retained source, exact pinned data, policies and identity,
including corrupt negative controls and 48 actual HTTP reads. This complements
Archive custody proof; Archive does not itself evaluate the workbook projection.

Archive restart `d38a01` exit 0 replaced only its owned HTTP process. The same
PostgreSQL/store retained all four tables, eight objects and the full guard
unchanged; fresh eight-document HTTP proof `fdc9c7` exit 0 passed. Custom dump and
actual isolated restore `9b8339` exit 0 created a new UUID database inside the
owned PostgreSQL container and a separate copied object root. All table rows,
objects and the complete native CHECK expression matched. Fresh native API
process proof `81efee` exit 0 read all eight restored documents without dependency
overrides; source records remained unchanged and restored read audit only appended.
Independent post-restart reader `40fc0c` exit 0 made 40 further HTTP reads and
verified process generations, bytes, identities, current chains and tenant refusal.

Final backup `c9951f` exit 0 retained custom dumps/TOCs and complete unchanged
snapshots for both databases. Scoped retirement `7464e6` exit 0 proved the owned
HTTP/watchdog processes, PostgreSQL container and sole volume absent, including
ports 55888/55491. Original/restored objects and backups remain retained.
Seal `d1bcca` exit 0 records 417 immutable artifacts in
`composite-eligibility-http-20261009-r7/final-manifest.json`, SHA-256
`0670408bc8e3104093689a5c7416a18c8fb4e9a8d16ed122637ff07b716f6a85`.
It also reverified all 56 R5 and 103 R6 artifacts unchanged. The
[issue evidence](https://github.com/sgajbi/lotus-archive/issues/188) is the public
index for retained campaign receipts and remaining acceptance.

## Remaining acceptance

R7 is controlled synthetic source replay using native local-development
PostgreSQL metadata/audit and filesystem objects, with explicit degraded readiness.
It proves this bounded custody/recovery path. Genuine monthly source amendment
remains dependent on [Manage #778](https://github.com/sgajbi/lotus-manage/issues/778);
no v1/v2 example or technical relationship substitutes for it. Issue #188 remains
open for its outstanding monthly amendment, pooled and institutional scope.
This evidence does not close Report #417/RPT-04, programme #923, source/checker
authority, production IAM/capacity or enterprise recovery qualification.

The earlier manual-checkout/wiki-junction/recovery-ref cleanup remains retained
after automatic approval review rejected removal. No retry or bypass is part of
this delivery. Prior R6 backups, objects, failures and sealed packets are immutable.
