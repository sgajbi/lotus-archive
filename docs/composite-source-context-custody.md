# Financial replay and source-context custody

Report `composite_review.v8` uses template `composite-review/v8`, qualification
`EXPLICIT_RETAINED_CALCULATED_REPLAY` and publication state `NOT_ATTESTED`.
Archive retains the cohesive financial identity, supplied definition/membership
pins, opaque Report revision and exact XLSX bytes through the existing routes.
Frozen v1–v7 identities, migrations and historical records remain unchanged.

The required `source_context.definition` equals `definition.pin`; its response
digest equals `definition.source_response_digest`. Every primary financial window
retains that definition content hash. Source context requests since-inception,
one or two membership revisions, or both. Membership revisions are unique; when
supplied, their content hashes cover every primary financial window. An additional
direct-parent membership pin is retained without inferring its history relationship
from a hash. Source-side original history and parent validation belong to Report.

Optional `source_products` retain up to eight uniquely keyed calendar/trailing
products. Existing v2 validators enforce scope, complete-month horizons, response
digests and exact primary window subvectors. Empty optional products serialize as
omitted, matching the producer. Source-context schema definitions are pinned to
Report's schema; the consumer adds custody joins without calculating returns,
rechecking source cryptography, evaluating eligibility or conferring publication
authority. Archive remains the custodian of generated-document evidence.

## Rollout and recovery

Apply pending migration021 after020 before enabling v8 writes. It extends the scope
constraint and adds two immutable, strict JSON structural helper functions for
unique pin keys and exact product/window correspondence. These functions query no
source tables. Keep v8-compatible readers, functions and schema while retained v8
records exist. Disable admissions and forward-fix rather than replaying020 over v8.

The required PostgreSQL proof seeds all seven legacy families under020, verifies
their full rows before/after idempotent021, admits both actual handoffs and two
optional identity controls, and reopens all eleven records in a separate process.
Valid direct INSERT/UPDATE controls accompany invalid direct INSERT/UPDATE pins,
scope/template refusals and atomic rejection of old020. Fresh reads verify bytes,
opaque revisions, identities, correction/current traversal, retention, source events
and foreign-tenant refusal. An unconfigured local database skip is not SQL evidence.

From the `lotus-archive` checkout, using its installed development environment:

```powershell
python -m pytest tests/unit/test_composite_source_context_identity.py tests/integration/test_composite_source_context_custody.py
python -m pytest tests/integration/test_postgres_composite_source_context_upgrade.py
```

```bash
python -m pytest tests/unit/test_composite_source_context_identity.py tests/integration/test_composite_source_context_custody.py
python -m pytest tests/integration/test_postgres_composite_source_context_upgrade.py
```

The database command uses the dedicated test DSN `LOTUS_ARCHIVE_TEST_DATABASE_URL`
and clears test rows. The owning protected lane sets
`LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1`, making missing database proof fail.

## Producer correspondence and client example

Pinned Report main `c731799f9c88b7d078c68456ae442b847247c966` supplies
`contracts/composite_review.v8.schema.json`, raw SHA-256
`d64d0f3cd782b5c8a65c06c82ddc22f9ff23ec98709435fd7676908ccb5cd2f4`.
Render supplier `5c7d77591e71e229c30acef08f33a29e2e69b642` supplies original,
corrected, later-window and positive since-inception package identities.
`tests/fixtures/composite_source_context/producer_context_schemas.json` pins the
exact three context definitions for consumer schema correspondence tests.

`tests/fixtures/composite_source_context/original.handoff.json` and
`corrected.handoff.json` are complete actual Render requests, including XLSX bytes,
with raw SHA-256 respectively
`53e270dc2be6ed7459f4b519bace2a8b9366c0e2f02a29234b0a17b98d987c49` and
`02f684dc4e057f6ed1a7c446339f7cb5d50d615185e9330e9dbc7ba5651e4986`.
Git attributes preserve exact CRLF supplier bytes. Optional controls wrap exact
producer identities in explicitly synthetic XLSX transport.

A registered Render transmitter submits the unchanged request to `POST /documents`
with authorized tenant/region headers. Repeat the exact request after an uncertain
result; preserve the existing archive request and Report revision. Changed pins or
revision under that request return conflict. Retrieve metadata, checksum-verified
download, retention and source events through existing document routes. An authorized
lifecycle caller may explicitly correct the original to the separately archived
corrected document; historical reads keep the original while `/current` resolves
the successor. The executable component example is
`tests/integration/test_composite_source_context_custody.py`.

Component proof is separate from qualified protected CI/main, wiki publication and
Root's final joined campaign. Issue194's joined criterion and issue188's original v4
acceptance criteria remain open. Controlled facts and configured caller identity
confer no bank authentication, official financial authority, enterprise recovery or
all-report acceptance.
