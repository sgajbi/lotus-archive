# Historical policy evidence custody

Archive adds Report `composite_review.v7`, `composite-review/v7` XLSX and selection
`v3`. Qualification is `CONTROLLED_HISTORICAL_POLICY_EVIDENCE_REPLAY`; publication
remains `NOT_ATTESTED`. The required exact `calculation_boundary` states configured
identity controlled producer custody without cryptographic/bank acceptance or
financial calculation. Ordinary roots are v3; corrections are v4 with newest-to-oldest
receipt pins ending in exactly one v3 original. Definition versions are independent.
Frozen v1–v6 identities and old selectors remain unchanged.

Archive preserves opaque Report digests, the full typed identity and exact XLSX bytes.
Complete original raw policy bytes/credentials/events, normalized mappings, present
admission and operation intents/proofs belong to Report's source-bearing snapshot
and workbook. Archive does not project them into another ledger, evaluate policy,
recompute producer cryptography or treat caller proof as newly verified authority.
Manage owns original-format verification, trust pins/revocation and admission.
Configured actor/service headers do not establish authenticated bank provenance.
Production original-format and service-principal qualification remain unavailable.

Existing checksum/size, tenant/region authorization, immutable replay, exact downloads,
technical correction/current traversal, retention and legal holds apply unchanged.
The owning package `archive/composite_historical.py` reuses eligibility scalar/calendar
guards. No new size limit, endpoint, table, calculator, trust service or runtime exists.

Apply pending migration020 after019 through the existing deployment flow, before v7
writes. It replaces only the scope guard, preserving rows. Keep compatible readers
and schema while v7 exists; disable writes and forward-fix rather than replay019.
Required PostgreSQL proof covers populated v6 preservation, idempotent020, direct SQL
invalid axes and separate-process reads of all twelve controlled graph cases. Existing
populated v1–v6 upgrade proof remains required in the same owning lane.

From the `lotus-archive` checkout, run focused component proof on either OS:

```powershell
python -m pytest tests/unit/test_composite_historical_identity.py tests/integration/test_composite_historical_custody.py
```

```bash
python -m pytest tests/unit/test_composite_historical_identity.py tests/integration/test_composite_historical_custody.py
```

Database proof runs in the required owning CI lane with its configured database;
an unconfigured local skip is not database evidence. Fixtures use synthetic XLSX
transport with pinned Report selectors, not joined capture, actual source verification,
enterprise recovery or financial authority proof.

Implementation input Report fit r4 manifest:
`32b6090df4b52d8b175ea7c2475d41c3a7ace8a579538a8164dd809939f55f33`.
Manage schema r1:
`42f303700e1699774df2a8babd34eb32d79aee3a261ddb7f7b6ceed141834a2e`;
graph r1: `4b91c97835bcb2b00d095c0ce02009d9b519e81847966ac07e2557d64d644c57`.
All twelve custody identities retain the exact producer boundary field and selection.
Qualified producer main, protected consumer CI/main, wiki parity and joined acceptance remain release
conditions. Issue188 remains open for full delivery.
