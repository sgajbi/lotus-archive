# API Surface

Every operation `lotus-archive` publishes, taken from the generated OpenAPI document on `main`.
There are **22**: sixteen on documents, six operational. The behaviour behind them is in
[Document Lifecycle](Document-Lifecycle).

## Documents

| operation | purpose | permitted callers |
|---|---|---|
| `POST /documents` | archive a generated document | `lotus-report` |
| `GET /documents/{id}` | support-safe metadata | `lotus-report`, `lotus-gateway` |
| `GET /documents/{id}/download` | checksum-verified binary | `lotus-report`, `lotus-gateway` |
| `GET /documents/{id}/access-events` | who accessed this document | `lotus-report` |
| `GET /documents/{id}/retention` | retention posture | `lotus-report` |
| `POST /documents/{id}/purge-evaluation` | may this be destroyed, and why not | `lotus-report` |
| `POST /documents/{id}/purge` | destroy the bytes | `lotus-report` |
| `POST /documents/{id}/legal-holds` | place a hold | `lotus-report` |
| `DELETE /documents/{id}/legal-holds/{legal_hold_id}` | release a hold | `lotus-report` |
| `POST /documents/{id}/supersede` | a newer document replaces this one | `lotus-report` |
| `POST /documents/{id}/correct` | this document was wrong | `lotus-report` |
| `POST /documents/{id}/reissue` | same content, issued again | `lotus-report` |
| `GET /documents/{id}/current` | resolve the current document from any in the chain | `lotus-report`, `lotus-gateway` |
| `GET /documents/{id}/source-events` | bounded lifecycle projection for portfolio memory | `lotus-report`, `lotus-gateway` |
| `POST /documents/access-preflight` | batch access posture, advisory | `lotus-gateway` |
| `POST /documents/{id}/idea-lifecycle-decisions` | signed retention/hold/purge projection | `lotus-idea`, `lotus-report` |

The caller column is the whole authorization model — see
[Security and Controls](Security-and-Controls#who-may-call-what). It is enforced against a
header the caller sets about itself.

## Operational

| operation | purpose |
|---|---|
| `GET /health` | service health with identity |
| `GET /health/live` | process liveness only |
| `GET /health/ready` | drain posture and runtime posture; `503` when draining or unavailable |
| `GET /metadata` | service posture, runtime posture, supportability, build metadata |
| `GET /metrics` | Prometheus exposition |
| `GET /version` | source-safe build provenance |

`GET /version` publishes service version, repository URL, commit SHA, Git ref, build timestamp, CI
run id, image reference, image digest and digest posture. A locally built image reports
`not_published`; mainline CI records registry digest, scan, signature and attestation evidence.

Note that `/metadata`'s supportability block is a **static declaration**, not a measurement — see
[Operations](Operations#supportability-is-declared-not-measured).

## The archive contract

`POST /documents` takes the complete record of a generated document plus its bytes. `lotus-archive`
fetches nothing; everything it knows arrives here.

| group | fields |
|---|---|
| request identity | `archive_request_id` — the idempotency key |
| upstream lineage | `report_job_id`, `report_request_id`, `snapshot_id`, `render_job_id`, `render_attempt_id` |
| document identity | `report_type`, `portfolio_scope`, `portfolio_id`, `client_reference`, `as_of_date`, `reporting_period_start`, `reporting_period_end`, `frequency` |
| production provenance | `template_id`, `template_version`, `render_service_version`, `report_data_contract_version` |
| artefact | `mime_type`, `output_format`, content as base64 |
| scope | `classification`, `region`, `tenant_id` |
| retention | `retention_policy_id`, `retention_start_date`, `retain_until_date` |
| optional summaries | `reviewed_advisory_narrative`, `advisor_proposal_memo`, `idea_evidence_pack` |
| attribution | `created_by_service`, `created_by_actor` |

Validation is strict about combinations, not just fields: `mime_type` must be a concrete media type,
reporting period start must not follow its end, retention start must not follow retain-until, and
each optional summary is bound to the report type and template it belongs with. A reviewed advisory
narrative on anything but a `portfolio_review` using the `portfolio-review` template is rejected, as
is an Idea evidence pack outside a `proof_pack` on `proof-pack` with
`dpm_proof_pack_report_input.v1`.

**`tenant_id` is optional here and required to read the document back.** A document archived without
one is stored and then permanently unreadable — [#93](https://github.com/sgajbi/lotus-archive/issues/93).
Always send it.

The service returns a `document_id`, the storage coordinates it assigned, a SHA-256 `checksum`
computed and verified at write, and `size_bytes`.

### Idempotency

`archive_request_id` is the key. Re-sending the same request returns the existing document rather
than archiving a second copy. Re-using the identifier for a *different* document is
`409 duplicate_archive_request` — the identifier is evidence, and silently binding it to different
content would destroy that.

### Body size

Content arrives base64-encoded and is bounded before decoding, at
`LOTUS_ARCHIVE_MAX_DECODED_DOCUMENT_BYTES` (10 MiB by default). The encoded-character limit is
derived from the decoded limit, so an oversized document is refused without first being expanded in
memory.

## Batch access preflight

`POST /documents/access-preflight` answers, for a list of document ids, whether this caller would be
allowed each one. It requires trusted tenant and region context, performs a single repository batch
lookup, and returns results in the order requested with per-document `allowed` / `denied` /
`missing` / `unavailable` states. Adapter lookup timeouts map to `unavailable`.

It returns **no storage paths and no payloads**, and it is **advisory**: the single-document metadata
and download routes apply the same scope check independently and remain the access boundary. Nothing
downstream should treat a preflight `allowed` as authorisation.

## Error codes

| status | code | when |
|---|---|---|
| `400` | `metadata_validation_failed` | the archive request failed validation |
| `401` | `caller_context_missing` | `x-caller-service`, `x-actor-type` or `x-actor-id` absent |
| `401` | `caller_scope_missing` | `x-tenant-id` or `x-region` absent on a scoped read |
| `403` | `authorization_failed` | the caller service is not permitted, or document scope does not match |
| `403` | `lifecycle_decision_tenant_forbidden` | lifecycle decision requested outside the caller's tenant |
| `404` | `document_not_found` | unknown `document_id` |
| `404` | `document_binary_missing` | metadata exists, the object does not |
| `404` | `legal_hold_not_found` | unknown hold, or a hold on another document |
| `409` | `duplicate_archive_request` | `archive_request_id` reused with different content |
| `409` | `document_checksum_mismatch` | stored bytes do not match the recorded checksum |
| `409` | `legal_hold_active` | a hold blocks the purge |
| `409` | `purge_not_eligible` | retention has not elapsed, or no retention date exists |
| `409` | `supersession_conflict` | the transition would branch or cycle the chain |
| `409` | `unsupported_lifecycle_transition` | self-transition, purged document, or unknown type |
| `409` | `lifecycle_decision_idempotency_conflict` | decision key reused with different inputs |
| `422` | `validation_failed` | request body failed schema validation |
| `422` | `lifecycle_decision_document_invalid` | the document is not valid for a lifecycle decision |
| `503` | `archive_runtime_unavailable` | runtime configuration cannot serve the request |

`403 authorization_failed` covers two distinct situations deliberately: a caller service that is not
on the permitted list, and a caller whose tenant or region does not match the document's. Both are
recorded as authorization-denied access events with a specific internal reason code; the response
does not distinguish them, so the error cannot be used to probe which documents exist.

Every error carries a `correlation_id` and the service name. Bodies never echo document content.

## Correlation

`X-Correlation-Id`, `X-Trace-Id` and `traceparent` are propagated when supplied and appear in
structured request logs. Logs record the **route template**, not the resolved path, so document
identifiers do not leak into log aggregation.

## Read next

1. [Document Lifecycle](Document-Lifecycle) — what these operations mean in business terms
2. [Security and Controls](Security-and-Controls) — caller identity, scope and audit
3. [Architecture](Architecture) — how a request becomes a stored document
