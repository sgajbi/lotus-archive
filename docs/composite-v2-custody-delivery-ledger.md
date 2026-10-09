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

## Qualified main and genuine R5 custody

[PR #183](https://github.com/sgajbi/lotus-archive/pull/183) merged normally from signed
`435362d3635f0b006901d83303196ec84ce9a8cd` after all seven required checks passed.
Tested Archive main is `280f6d8d8b0ea47be3e35cbcb25b4347280c5920`;
[exact-main releasability 37902284796](https://github.com/sgajbi/lotus-archive/actions/runs/37902284796)
succeeded. The initial authored wiki was published at
`b2da84a902274fed22c6b4357339415895c0a6e6`, with strict committed parity on all ten
pages. Root independently reviewed the actual original/corrected identities,
actual retained v1, eleven bad inputs and unchanged migration014 (`1c2ac1`, exit 0).

Only after Report `89b4fa0dfae10b26ae20f16727dccff36a069a49`, Render
`383126231bb7744d6b4f3f60436ded86da5f0085`, and Archive's exact mains qualified did
the single `composite-source-products-http-20261009-r5` phase start. It used fresh
Archive HTTP 55885/PG 55487 and isolated files, with explicit local-development
health disclosure. The registered Report ASGI API and real PostgreSQL worker
processed the accepted frozen Performance responses through actual Render HTTP
and Archive HTTP. Controlled source replay and `NOT_ATTESTED` remain explicit.

Producer native `53fe90`, exit 0, sealed 28 artifacts under manifest SHA256
`c604ffe85ce32c529443ac531ea9fa668af1ef3f281fd69c51e955b82e7d0ae5`.
Native intake `c80b08`, exit 0, independently verified every file, integer native
exit 0 and all three unchanged clean source bindings. No second producer/source
campaign was run; technical rerender fetched no new source responses.

| Retained version | Archive document | Full XLSX SHA256 | Bytes |
| --- | --- | --- | ---: |
| Original | `doc_1d48345844124e57bc6bf61799588f1b` | `e6d552ff1c3c61a66db0058f2ec35d188be210dd13d4ba1bbdde1a5e5b9a6a7f` | 1,318,499 |
| Financial correction | `doc_5255e4b8e9894a25af716174e1dd859c` | `1efcaf0b5e1faf5b0d4dcce83d7df4bfc9b9407c924335e9e46092983cc2d686` | 1,319,433 |
| Retained-original technical rerender | `doc_773cd8003203444a826fc5ec8617f7b4` | `33f88c9e229351594ff79ecb098813e519c65d3bd6c43c852baaf2241572936c` | 1,318,533 |

Owning consumer `469837`, exit 0, proved all three full identities and downloads
equal actual producer output and the frozen source pair. Each retained primary
72-window vector and calendar 2020/trailing 12-month product retained its own complete
pins and response digest. Source events preserve the complete v2 identity.
Actual Archive HTTP exact retries returned 201 with the same record; changed
product order or agreed source digest returned 409. Foreign metadata, download,
source-event and retention reads returned 403. The authorized QA correction from
technical rerender to financial correction returned 201 and was exactly retryable;
foreign correction returned 403. Original-current resolves financial correction.
Real PostgreSQL contained exactly 3 documents and 2 relationships. Report supplies
the technical link; authorized Archive QA supplies the financial link.

Root independently accepted ten live HTTP reads, all three complete workbooks,
24,623 canonical/display cells and 81 policies per workbook, source products and
the actual correction chain (`3637fe`, exit 0). Receipt SHA256:
`61996f8de6788bedd058a862ba4dbfcee173f9416652ea2d6aa803e54e729797`.

## Restart, backup and owned retirement

After Root's pre-reader accepted, owned HTTP 98052 stopped (`f548ab`, exit 0) and
HTTP 90124 reopened the same PostgreSQL, volume, files and schema (`b8e715` and
`611fec`, exit 0). No historical migration was replayed. Post-restart custody
`a03458`, exit 0, repeated the full owning checks; exact comparison `693657`, exit 0,
proved all nine metadata/source-event/workbook files byte-identical, the same
retry/current response and persisted lifecycle/denial audit. Restart receipt SHA:
`00757b40455c53628706b6145cb5167806d8493c6bcf0a75907168780488b0cb`.

Root independently accepted ten fresh post-restart HTTP reads and exact retained
metadata/workbooks/current chain (`f2489d`, exit 0), receipt SHA256
`bb63dc7c82a4b6d3b4ac2cfc080ab392ada0badd2fc75ff812261c99eab1b515`.
Only then did final `pg_dump` complete (`3caa00`, exit 0), before copy and readable
custom-format TOC proof (`fb6eb2`, exit 0). Retained backup
`archive-source-products-r5-final.dump` is 78,701 bytes, SHA256
`edf94fe6c95ab24ca7043cc9bccdc3941e36e1760c2d0c2a104cff771566b2a1`.
Inventory `c7a894`, exit 0, records 3 documents, 107 audits, 0 legal holds, 2 relationships
and all three retained exact object bytes. This does not claim full restore certification.

Exact owned HTTP, PostgreSQL container and anonymous volume retired (`11f7df` and
`f77f85`, exit 0); absence of owned Python processes, listeners 55885/55487, container
and volume passed (`3b5a81`, exit 0). Retained object/backup integrity and unchanged
historical R2/R3/R4 backups passed (`3874c7`, exit 0). No foreign resource or canonical
stack changed. Final backup/cleanup receipt SHA256:
`6db6075accb892c2f843a50449dc76d5b5c9231c07ed413ac86c7c17c460b126`.

Root independently rehashed the final Archive dump, all three retained objects,
producer/Render copies and the sealed 28-file producer manifest, and verified
all phase-owned containers, volumes, seven recorded process IDs and four ports
absent/closed (`0bc44c`, exit 0). Final independent receipt SHA256:
`f1ac36ca73ed66a8d24062c0d8c79f6718353a9c9b20dfc9b3868b399c8b68d5`.

## Closure revision correspondence

This evidence revision changes documentation, authored wiki and the owning
PostgreSQL regression only. Runtime source tree remains
`297eb6344252c531a183706fae26fa87eef2cd09`; migrations tree remains
`1f61cad3c773d40c914fdba07f546eecc4c0cd0d`, exactly the tested `280f6d8` main.
The regression also asserts that replaying historical 014 over retained v2 refuses
atomically, preserving every full retained row and the compatible 015 constraint.
Recovery keeps the compatible reader/schema and disables admissions to forward-fix.

Issue closure requires this truth on qualified main, current required checks,
published authored wiki with strict committed parity, and a verified issue evidence
comment. Custody grants no official approval, all-product or enterprise completion.
