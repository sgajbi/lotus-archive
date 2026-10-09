# Eligibility evidence custody acceptance

[Issue #188](https://github.com/sgajbi/lotus-archive/issues/188) extends the existing
Composite XLSX custody path with Report-owned `composite_review.v4`. Its strict
selection retains Manage eligibility evidence rather than inventing a Performance
calculation. Component admission is proved; PostgreSQL and actual coordinated
Report→Render→Archive execution remain separate acceptance requirements.
Completed v1/v2/v3 custody and their sealed evidence remain unchanged.

## Source and authority

The Report-owned corrected r2 interface freeze has receipt SHA-256
`98fdf10551e464396443540aa28179f81d29b5164d1fe28a22623e3f3e0809d0`.
Its dataset schema SHA-256 is
`2214d2044980fc81007637e0504a46d13b2cbf10959fd2ca2198d2ed5f557e73`;
the strict selection schema is
`cd71b7ab72fc9fd5493ca399e3a1f53690b426b8d652628e0b70a40c54f53171`;
the interface matrix is
`3c3d131d88cdfc7e0f5a5b8531db081311768544bc86a725d2180c9be944eb3c`.
Archive intake `4d7467` exit 0 verifies all three byte counts and hashes. This is
an output-wire freeze, not signed source or actual runtime acceptance.

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
parallel source projection. Coordinated acceptance must bind the full fresh
Report snapshot/package and actual Render bytes to the retained Archive identity.

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

## Proof and remaining acceptance

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

Required PostgreSQL execution, protected PR/current main qualification, authored
wiki publication/parity and the actual source-qualified joined campaign remain
pending. Exact public issue evidence must be posted and read back before closure.
This slice does not close Report #417/RPT-04, programme #923, genuine source/checker
authority, production IAM/capacity or enterprise recovery qualification.

The earlier manual-checkout/wiki-junction/recovery-ref cleanup remains retained
after automatic approval review rejected removal. No retry or bypass is part of
this delivery. Prior R6 backups, objects, failures and sealed packets are immutable.
