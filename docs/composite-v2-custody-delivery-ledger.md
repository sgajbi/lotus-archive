# Composite v2 custody delivery

Owning task: [lotus-archive#182](https://github.com/sgajbi/lotus-archive/issues/182).
Parent: lotus-platform#923. Report #417/PR423 and Render #344/PR345 own the
upstream v2 package and workbook. Completed v1 #176 and its R2/R3/R4 evidence
remain unchanged.

Base: `3834ea25e0e2fc2d4d0edfc202490575370fd552`. Owner branch:
`feat/composite-v2-custody-182`, isolated existing Archive owner checkout.
Primary and foreign checkouts remain read-only. Intake and pre-PR fetch/prune
found no unmerged remote durable truth.

## Implementation and controls

The existing input/response/source-event models admit a discriminated union of
unchanged v1 identity and strict v2 identity. Typed calendar/trailing pins reuse
the existing selection/window models. The existing writer, immutable repository,
object storage, idempotency, correction, retention and authorization paths retain
the complete ordered identity. No endpoint or financial authority is added.

Migration 015 replaces the owning scope check additively, preserving migration
014 and all retained rows. Mixed identity/template/data axes, invalid composite
scope, non-replay authority and empty/malformed/oversized v2 product arrays refuse
in PostgreSQL. Full inner product typing and primary-subvector validation belong
to the application contract, as primary selection validation already does.

The [custody contract](composite-custody-contract.md) contains internal identity
definitions, operator upgrade/recovery instructions and executable client retry
examples. Authored wiki API Surface and Operations change with this slice.

## Evidence boundary

Fixtures retain actual R4 v1 metadata and the frozen Report original/corrected v2
custody contexts. V2 provenance is shared-contract-r2 manifest SHA256
`f0b3c41d829857605a7731faa6a0258d7f6ee4a39b661374a438612025eb99c4`;
original package SHA256
`2285991971739d839c9ca1cf7f6a1e439fac571266d8ed27b498a3ab1c255d77`,
financial-correction package SHA256
`5c029414d124f8d58ee566632d5bd5373abace93f5635aff28f3d83c365d5f84`.
Local component tests use synthetic transport workbook bytes, explicitly distinct
from the actual workbook candidates and genuine qualified producer HTTP chain.

Native local proof before promotion:

- Existing v1 identity tests: 14 passed (`4ba7cd`, exit 0).
- Actual retained v1 and v2 identity controls: 38 passed (`d7512b`, exit 0),
  including all six mixed axes, ordered identity and valid 1/8 product boundaries.
- PostgreSQL populated upgrade and separate process reopen: `ace5b9` plus terminal
  `8eb087`, exit 0. Full v1 SQL row unchanged; v1 retries and all three records'
  bytes/identity/current resolution preserved. Refusal controls execute against
  actual PostgreSQL, not a repository double.
  Final strengthened proof `c01286`, exit 0, also reapplies 015 over populated
  v2 rows and rejects a nine-product array at the database boundary.
- Separate full lanes: 551 unit tests passed (46 skips), 142 integration tests
  passed with PostgreSQL proof required, 9 end-to-end tests passed. Eight further
  version/boundary unit cases passed in the focused 38-case proof above.
- Combined coverage 99.44%, new source-product module 100% (`763cfc`, exit 0).
- Lint, typecheck, code health, OpenAPI and migration gates passed (`c3b31f` plus
  terminal `26e9df`, exit 0); dependency vulnerability audit passed (`02e957`, exit 0).
- CI-configured pyramid passed (`a9b32b`, exit 0). A diagnostic invocation with
  database-only modules collected has an existing integration-ratio failure;
  required database execution is still run and evidenced separately.

## Release acceptance still required

Component proof does not close #182. Current required exact-head CI and reviews,
normal protected merge, exact-main releasability, authored/published wiki committed
parity, and fresh qualified Report→Render HTTP→Archive HTTP R5 original/correction,
retained-original retry, tenant refusals, full bytes/identity, restart and owned
resource disposition remain required. R5 stays offline until all three compatible
main heads qualify. No official approval, all-product or enterprise completion
is inferred from this custody seam.
