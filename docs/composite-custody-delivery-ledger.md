# Composite custody delivery ledger

Engineering task: `lotus-archive#176`; parent `lotus-platform#923`;
producers `lotus-report#417` and `lotus-render#338`.

Owner checkout: `<workspace-root>/worktrees/lotus-archive-composite-176`,
branch `feat/composite-custody-176`, admitted base
`9c74fd01d00f3e66dda65a5612c69038307d61c3`.
The primary Archive checkout remains read-only. No foreign changes or worktrees
were present at intake. `git fetch origin --prune` and
`git branch -r --no-merged origin/main` found no stranded branches.

## Intake and evidence boundary

Archive is the shared custody capability; Report owns factual identities and
Render owns workbook production. Existing `ArchiveDocumentInput`, writer,
filesystem/S3 storage ports, PostgreSQL metadata/audit repositories, registered
document API, retention and lifecycle transitions own this extension. No new
runtime service, storage, ledger, financial calculation or distributed transaction
is warranted. Existing writer and registered API tests are the closest tests.

The registered `POST /documents` refused `composite_review` with HTTP 422
`validation_failed`; the otherwise identical `portfolio_review` request under
the permitted `lotus-render` caller returned HTTP 201. This is API component
evidence with real filesystem bytes, not Report→Render→Archive acceptance.

The baseline scope required a portfolio ID in DTO and PostgreSQL. Root coordinated
exclusive composite scope and exact Report producer fields before schema mutation.
Migration 014 adds nullable composite identity with exclusive persisted-scope guards.
XLSX validation belongs to `archive/artifact_format.py`, invoked by
the existing writer before replay/storage. Synthetic OOXML fixture proof is
explicitly distinct from the actual Render output and actual source-qualified
producer chain.

## Closure posture

Status: Archive implementation merged and mainline validated; producer acceptance
remains open. [PR #177](https://github.com/sgajbi/lotus-archive/pull/177) merged to
`c1a8dbd58e422bc2a5e6a48e7cff338531be91b7` after all seven required exact-head
checks passed on signed `f25e66766b3737b8c5527bb89a8c3cf0fae77410`.
[Main releasability run 37865598868](https://github.com/sgajbi/lotus-archive/actions/runs/37865598868)
passed on that exact merged revision, including database suites, coverage,
security, image signature and provenance. First RPT-01 custody does not establish all
twelve report products, official/GIPS authority, financial publication approval,
enterprise scale or full composite readiness. Candidate qualification remains
`EXPLICIT_RETAINED_CALCULATED_REPLAY`; publication remains `NOT_ATTESTED`.
Issue #176 remains open for completed producer orchestration and a qualified
actual corrected-source artifact. Mainline CI and authored wiki publication have
passed; actual controlled candidate custody and template rerender are proved
below. Neither recorded transport nor controlled source admission establishes
joined live acceptance.

Source docs, wiki, repository context and supported features changed together.
No central skill/routing change is needed: existing backend and custody patterns
own the extension. No CI workflow change was made.

## Local durable adapter proof

Owned PostgreSQL test container: `lotus-archive-composite-176-pg`, image
`postgres:16-alpine` matching current CI, container identity
`a11e7ce1632542e8c7397b7baab8cb9b5090f21aa15b50bb3fd940b60beaff6e`,
loopback port 55476, `engineering_task_id=lotus-archive-176`,
`owner_thread=01a11dfb-ccda-7512-b071-7c3cc70b879c`. Native creation/readiness
and label inspection exited 0. Four focused registered API tests passed actual
PostgreSQL migrations, durable metadata/audit, filesystem bytes/download,
retained correction, cross-tenant refusal, restart/retry, immutable pins and
raw-SQL scope/authority guard rejection. No shared or canonical stack was changed.
Separate native-equivalent suite processes passed: unit 520 (45 explicitly
optional skips), integration 141 with required real database, E2E 7. Combined
coverage gate passed 99.42%; security audit found no known vulnerabilities.
Typecheck, lint/format, OpenAPI, migration coverage, monetary-float, dependency,
dead-code, complexity, source-size and test-pyramid checks passed. An initial
all-suite single-process diagnostic failed because the existing E2E runtime
state polluted later health checks; the governed separate process suite model
resolved that without a runtime mutation. Only successful runs are acceptance
evidence. The owned database and anonymous volume were removed after exact
identity/label verification; native cleanup and residual checks exited 0.

Quality decision: retain max CC 18 and zero D–F functions; extract decoded-content
admission into the artifact owner and ratchet the measured source-size ceiling
913→910. No weaker guard or suppression was introduced.

## Consumer coordination

Report's registered PostgreSQL worker-produced candidate package was independently
read at SHA-256 `036beb4e84c76c047ce1c0c847a54d3bbc3505110f00f3753c7a25f024729ff5`.
Its context agrees with the Archive typed contract: tenant-a/APAC, genuine
`NEUTRAL_BALANCED`, null portfolio ID, exact 2026-01-01..2026-02-28 horizon,
two retained window pins, three Report lifecycle digests, and revision
`rrv3_946e4c00c3a949d03bbce6e2c00a4df2a84c80396042b1a3ea91d2caa6b45e32`.
This candidate consumes controlled Performance evidence and explicit test-only
Report family admission. It establishes real Report package production,
registered Render workbook production and registered Archive custody. Committed
producer parity, live source acceptance and official approval remain unproved.
No missing source retention policy or retain-until date was invented.

The actual original workbook was archived/downloaded with identical 33,667 bytes
and SHA-256 `e02ddad3d6be95c7628b3a25959c969ea76c2f852058c3287b81621ed8116d0e`.
Metadata and source-event identity matched the supplied producer context;
cross-tenant read/download/events/retention/create refused 403 with durable
audit. Reconstructed repositories replayed the same retained document, while
changed factual pins under its archive request refused 409. The producing
command exited 0 on exact merged Archive main. Evidence was posted and read back
in [receipt 6071891531](https://github.com/sgajbi/lotus-archive/issues/176#issuecomment-6071891531).

Render then emitted a revised development template using a distinct real archive
request, render attempt and template digest, preserving the Report snapshot and
revision. Both actual supplier artifacts were retained in one owned PostgreSQL
and filesystem custody environment. Revised bytes (33,668 bytes, SHA-256
`a58464d5f45f6bb4432cf8245947a0a71e644dd86e445cd0bc0ddcdf8f8e28e2`)
were created and downloaded through registered APIs; duplicate submission returned
the same document. Deliberately reusing the original archive request for revised
bytes refused 409 without changing the original. An explicitly controlled
operator validation of `/reissue` returned 201; `/current` resolved the revised
document and the original remained downloadable with its original checksum.
This is a template rerender of unchanged financial facts, not a corrected
financial-source producer artifact. Source events and actual creation and
relationship responses were captured for producer transport validation.
The producing command exited 0; [receipt 6071940249](https://github.com/sgajbi/lotus-archive/issues/176#issuecomment-6071940249)
was posted and read back. The separate owned rerender PostgreSQL container and
volume were also removed with ownership and absence verification, native exit 0.
No primary checkout or canonical/shared stack was changed.

Final gate review found the added unit guard proof put E2E breadth below its
1.5% floor (7/467). The complete registered create→download→correct→hold product
journey was classified in its owning E2E suite, retaining the same shared
scenario for the real PostgreSQL integration test. No count-only test or gate
threshold change was added. Final suite counts/coverage supersede the pre-freeze
counts above after this classification correction.
The final pyramid passes at unit 353, integration 106, E2E 8 product tests;
focused E2E/real-PG/API verification passed 25 tests. Typecheck and lint passed.
Pre-merge source-authored wiki parity check passed with the intentional two-page
unpublished-source delta. Post-merge publication succeeded at wiki commit
`08d87bd7de724b5d9c0fc2dfb852fe3d5d2c95d8`; strict native parity passed and all
ten source/published committed blob SHAs matched. Exact-main targeted API,
real-PostgreSQL and E2E verification passed 18 tests without skips.

Remote feature history was deleted by the normal merge, and `git cherry`
confirmed all three local feature patches are present on main. The clean owned
worktree, wiki-source junction and local feature branch were retained after
automatic approval review rejected their cleanup command as `blocked by policy`.
They contain no unique unmerged durable truth; no foreign work was reverted.
