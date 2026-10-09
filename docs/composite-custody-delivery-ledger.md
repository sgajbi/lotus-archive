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

Status: Archive implementation merged and mainline validated; the subsequent
supported-producer financial correction phase below completes the bounded
custody proof. Final delivery reconciliation remains open until this evidence
is on validated main and the authored wiki is published.
[PR #177](https://github.com/sgajbi/lotus-archive/pull/177) merged to
`c1a8dbd58e422bc2a5e6a48e7cff338531be91b7` after all seven required exact-head
checks passed on signed `f25e66766b3737b8c5527bb89a8c3cf0fae77410`.
[Main releasability run 37865598868](https://github.com/sgajbi/lotus-archive/actions/runs/37865598868)
passed on that exact merged revision, including database suites, coverage,
security, image signature and provenance. First RPT-01 custody does not establish all
twelve report products, official/GIPS authority, financial publication approval,
enterprise scale or full composite readiness. Candidate qualification remains
`EXPLICIT_RETAINED_CALCULATED_REPLAY`; publication remains `NOT_ATTESTED`.
The earlier phases left corrected-financial-source custody unproved. Mainline CI
and authored wiki publication passed for those phases. The actual
Performance-wire candidate and registered retained
rerender below prove genuine Render-to-Archive HTTP custody and Report-to-Archive
lifecycle orchestration. Performance input/verifier and Report XLSX catalogue
admission remain controlled; Report adopts captured genuine sender responses.
This bounded proof does not establish official or fully live financial-source
acceptance.

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

## Actual Performance-wire candidate and retained rerender

The subsequent Report package consumes an actual registered Performance main
response from `c100c885752c86b8d950d7970c99a8d223e6376a`, with controlled synthetic
inputs and verifier. Report runtime source is main
`02052b4c95b88e6fafa6254aa3bf283cfc007c97`; XLSX catalogue admission remains
test-only. The new package SHA-256 is
`ead799a97341533ec9e267424de959424f4260abc0fb83c8e18658bf4ee5b5b0`, with genuine
composite `SYNTHETIC_OR-02`, null portfolio ID, job
`rjob_5922448d2e084525ade847752baa2852`, snapshot
`rsnap_a9a271444add44a1bd71cea447932a48` and revision
`rrv3_55832129dbec2790a54020a7712ef55ebc87dc4f36ca52da9d2551e94fefbb13`.
Earlier synthetic/historical document identities were not spliced into this chain.

Clean Render main `f3670e577137491caafe102a58074055836a80c4` produced the workbook
and transmitted it with its unmodified `StdlibArchiveTransport` to unchanged
Archive main `f05d0f0c46b2b208dfadc9fa99dc88fabda2e79b` registered routes, with
explicit owned diagnostic PostgreSQL/filesystem/audit adapter bindings. Actual
HTTP POST returned 201, document `doc_ae12cc642013499094177eebc253f40c`, request
`areq_0cce4b565b0941489fbad6c54a00e2f3`. Independent authorized Report HTTP
metadata/download returned 200, exact 35,178 bytes and SHA-256
`25dc83decb917cddde772b9848f6690e3ae533d8ed9192e779ad4c3db9f2f860`.
The independently recomputed bounded XLSX member fingerprint is distinct:
`febdb210fb816326d1b997eb5d8b378a34af3accf3a65cf5a3239c21f47109d1`.
Render's initial diagnostic exited 1 after successful ingest because its ingest
principal correctly received download 403. The preserved successor complete
producer command exited 0 using the existing Report read boundary; no policy
was weakened. Render independently reconciled 162 canonical and 162 display
cells, the full pinned dataset and raw bytes. Archive verified every producer
metadata pin, genuine replay 201, foreign-tenant read/create 403, malformed XLSX
400 before replay, changed revision under the same request 409, request-ID
recovery and persisted access/source/retention receipts. These native-exit-0
receipts were posted and read back in
[6072429820](https://github.com/sgajbi/lotus-archive/issues/176#issuecomment-6072429820).

Report's registered PostgreSQL worker adopted that genuine captured sender
receipt after a controlled lost-response/restart: one source call, one submit,
one recovery lookup and unchanged snapshot. The same Report database then
issued registered rerender package SHA-256
`bb71ffbd8bfc8d8accda9bf72f2e6a803bd57e0fd237849214a32212c53351c2`, changing
only render job to `rdr_rrnd_1133e1085f364963b6596b42056c71e2_xlsx`.
Render again used genuine HTTP transport to the same Archive database and
received document `doc_47daf239ddc644ab80844db4c319376e`, request
`areq_665c29c98316fbf800eea64fc07e359e`, 35,200 bytes and SHA-256
`8a6764ac195c0654bb2387679e3e1b860f3f24ad3d6575e48723914b1eb8af50`.
Report's unmodified `ArchiveClient` then posted the original-to-rerender
`/correct` lifecycle call over actual HTTP, returning 201. Report's same-key
retry reused the attempt; its producer command completed with native exit 0.

Archive independently verified both exact downloads, all supplier metadata
pins, equal snapshot/revision/source identity, reciprocal relationship fields,
original `/current` resolving to the rerender, persisted Report lifecycle audit,
source-event composite scope, both replay 201 responses and foreign-tenant
download 403. The lifecycle relation is `correction`, but the financial dataset
is unchanged: this is a technical retained rerender, not a corrected financial
source. [6072497586](https://github.com/sgajbi/lotus-archive/issues/176#issuecomment-6072497586)
records the independently verified pair proof.

After explicit coordinator phase completion, verified owned HTTP processes
were restarted while retaining the database/filesystem. The bare pair verifier
exited 0 after restart (`7040f6`), preserving bytes, identities, current resolution,
relationships, audit, replay and tenant refusals. Final native database backup
and copy exited 0; preserved backup SHA-256 is
`1ab5164e1e0d74541af596f905f167d71ca8d9c05c807d5c14db04cb50493cb3`.
The exact owned processes, labelled PostgreSQL container and verified volume
were removed and their absence verified with native exit 0. Objects, workbooks,
receipts and backups remain preserved; the diagnostic endpoint is no longer
live. [6072522307](https://github.com/sgajbi/lotus-archive/issues/176#issuecomment-6072522307)
records restart, backup and cleanup. No shared/canonical runtime was affected
and previously policy-blocked worktree cleanup was not retried.

This evidence establishes the bounded registered producer custody and technical
rerender relationship. It retains `EXPLICIT_RETAINED_CALCULATED_REPLAY`,
development template and `NOT_ATTESTED` qualification; it does not establish
qualified financial correction, official authority, all twelve report families
or enterprise capacity.

## Supported producer and financial correction phase

Phase `composite-supported-report-http-20261009-r2` used a fresh owned Archive
instance at clean main `524d4d607712324b6f04a980590d55cf1db55ca9`. No document
identity or database from the previous phase was restored. Actual registered
Performance main `c100c885752c86b8d950d7970c99a8d223e6376a` produced the matched
original and financially corrected calculated responses: calculation IDs
`a9686913-27da-49d6-a12a-1b77b89c906e` and
`95d340cd-1545-4075-acef-aae8fd5008fc`, respectively. The handoff SHA-256 is
`41016a8db54e4fd26d57f76bc6b1532bf79f1e8d18e2735416399ebf6d111860`.
January materialization changed from sequence 1 to 3; the retained February
window stayed identical. The source cumulative figures changed from 3.02% to
5.57%. Archive checked each artifact against its own source vector, without
recalculating financial figures or requiring equality across a financial correction.

Report's signed producer `e7737eab3dab0493529c69fd7ba1a9f4927f31c9` used normal
supported `composite_review` XLSX admission, registered PostgreSQL orders and
unmodified RenderClient/ArchiveClient. The actual producer command
`exec-7141cc91-d8e6-40b6-8778-c2ec4cbf810f` completed with native exit 0.
Performance response intake remained a frozen matched controlled response pair;
Report-to-Render and Render-to-Archive were genuine HTTP. Render main
`162016d4a64769b31c90511f7604c145929979f0` supplied its actual catalogue and
workbook production. Report [PR #420](https://github.com/sgajbi/lotus-report/pull/420)
subsequently merged as `bbc1d65f64357e2267002fff0b1db76505a14317` from final
head `2705df948b478364052948e75d76fa0e8e1dc829`; exact-main releasability is
a separate final-delivery dependency, not inferred from the producer result.

All three artifacts carry genuine composite `SYNTHETIC_OR-02`,
`portfolio_scope=composite`, null `portfolio_id`, controlled source/verifier and
`NOT_ATTESTED` publication:

| Artifact | Retained document | Bytes | Exact raw SHA-256 |
|---|---|---:|---|
| Original | `doc_d9ca4116c60c4a0897ddd102eb9d1db0` | 35,181 | `28a986ac6197897d7a114fdd7578c494ed8ee8e9484fa715164a7309f86fc018` |
| Technical retained original rerender | `doc_aeda2ce252a44354b6cb51d525a00b79` | 35,202 | `4f277ba036a656f95d0f40dfe9f36f2667d67f5884053f5740592c5eeedf34a7` |
| Financially corrected | `doc_cd52613e0e724eb28d9f36b79238d9a8` | 35,190 | `fd42d9004c2c59f91313999759cb6c7b6cc26d4c5570c2e1534bb36028b2d148` |

Report's actual ArchiveClient linked original to technical rerender. After
the producer completed, the coordinator-authorized Archive proof used the
existing controlled Report service principal and registered `/correct` API
to link technical rerender to financial correction. This second lifecycle
call is owner API proof, not a claim that Report orchestrated that financial
relationship. All reciprocal links persisted; `/current` from the original
resolved to the financial correction, while all three remained downloadable.
No authorization policy was weakened.

Independent Archive proof checked each actual producer package/wire identity,
own report/snapshot/revision/render/template pins, typed source identity and
retained vector, raw download/filesystem/producer byte equality, MIME/extension,
source events, access audit and retention. Independently bounded ZIP-member
fingerprints matched their declared values. Explicitly reconstructed ingest
replay returned the same document; changed revision under the same request
returned 409, malformed XLSX was refused before replay, foreign tenants were
refused 403, and the Render ingest principal remained unable to read. Native
proofs exited 0; [receipt 6072995170](https://github.com/sgajbi/lotus-archive/issues/176#issuecomment-6072995170)
was posted and read back. Existing mainline PostgreSQL hold/purge fencing and
immutable-pin guard tests remain the authority for those adapter behaviours.

The coordinator independently read all three actual HTTP artifacts and reconciled
each workbook's 162 canonical/display values, 62 policies, 13 tables, 17 sheets
and complete pinned dataset; Decimal results were 3.02% and 5.57%. Its qualified
reader command `e40aab` exited 0. Only after that reader window completed did
Archive restart its exact owned HTTP processes against the same PostgreSQL and
filesystem. Postrestart custody `535729`, lifecycle `0024a7`, producer-pin/replay
guards `944f3b` and consolidated preservation `17fef2` all exited 0. All three
full metadata responses and exact bytes, current resolution, lifecycle retry,
audit, source and retention receipts remained intact.

Final native database dump/copy exited 0, preserved at SHA-256
`9ab96528138f9ff0e8f40e58c69f7ae54c2ad9579b7dc57457e3c26e099ae377`.
After exact process ancestry/entrypoint and container owner/task/phase/volume
checks, only the owned processes, container and volume were removed. Cleanup
`b7b9a1`, `7b7e8d`, `1f3cbd` and absence verification `5ba80c` exited 0.
Retained objects, workbooks, receipts and backups remain; the endpoint is no
longer live. Canonical/shared runtime and foreign producer resources were untouched.
Previously policy-blocked worktree cleanup was not retried.

This phase proves the bounded original, technical rerender and financially
corrected XLSX custody requirement using the normal supported producer family.
It retains `EXPLICIT_RETAINED_CALCULATED_REPLAY` and `NOT_ATTESTED`: controlled
Performance intake/verifier, diagnostic real adapters and a development template
do not establish official authority, all twelve products or enterprise certification.
No source, migration, API, workflow or central context change is needed for this
evidence update. Authored wiki truth changes in the same slice.
