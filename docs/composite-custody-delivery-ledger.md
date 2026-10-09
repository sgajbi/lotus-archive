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

Status: implementation in progress. First RPT-01 custody does not establish all
twelve report products, official/GIPS authority, financial publication approval,
enterprise scale or full composite readiness. Candidate qualification remains
`EXPLICIT_RETAINED_CALCULATED_REPLAY`; publication remains `NOT_ATTESTED`.
Issue #176 stays open until its acceptance evidence is merged, validated and
posted/read back. Mainline CI, joined producer acceptance and wiki publication
remain pending.

Source docs, wiki, repository context and supported features will change together.
No central skill/routing change is needed: existing backend and custody patterns
own the extension. No CI workflow change is planned.

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
evidence. Cleanup of the owned database remains pending joined candidate proof.

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
This candidate consumes controlled Performance evidence; it is supplier
coordination, not committed producer parity, official approval or full readiness.
Render's actual output and Archive joined candidate acceptance remain pending.
