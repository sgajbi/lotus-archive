# Security and Controls

What protects `lotus-archive`, what it records, and what a deployment must provide because the
service does not. Measured against `main`.

## The controlling fact: caller identity is self-declared

`lotus-archive` performs **no authentication**. It reads the caller's identity from headers the
caller sets about itself:

| header | meaning | required |
|---|---|---|
| `x-caller-service` | which Lotus service is calling | always |
| `x-actor-type` | what kind of actor is behind the call | always |
| `x-actor-id` | which actor | always |
| `x-tenant-id` | the caller's tenant | on scoped document reads |
| `x-region` | the caller's region | on scoped document reads |

There is no token, no signature and no verification. Anything that can reach the port can send
`x-caller-service: lotus-report` and thereby hold every permission the service grants — including
placing and releasing legal holds and executing purges.

This is the standard internal-service posture in this estate: authentication and authorization are
assumed to be enforced by platform ingress and service-to-service policy before the request arrives.
Two things follow, and both are deployment obligations rather than service behaviour:

1. **Network reachability is the access control.** `lotus-archive` must be deployed as an internal
   service, never routed to the public internet.
2. **The authorization policy below is a blast-radius boundary, not an identity check.** It limits
   what a *correctly behaving* caller can do. It cannot resist a caller that lies about who it is.

Read every control on this page with that in mind.

## Who may call what

The policy is a fixed allow-list of caller services per permission, applied before any document is
loaded:

| permission | permitted callers |
|---|---|
| `create_document` | `lotus-report` |
| `read_metadata`, `download_binary` | `lotus-report`, `lotus-gateway` |
| `read_retention`, `evaluate_purge`, `execute_purge` | `lotus-report` |
| `manage_legal_hold`, `manage_lifecycle` | `lotus-report` |
| `read_access_events` | `lotus-report` |
| `read_batch_access_preflight` | `lotus-gateway` |
| `read_idea_lifecycle_decision` | `lotus-idea`, `lotus-report` |

`lotus-workbench` appears nowhere. Workbench retrieval is supported only through the Workbench BFF
and `lotus-gateway`; a direct Workbench call is refused because the service name is not on any list.

A denied call raises `403 authorization_failed` **and writes an authorization-denied access event**
with the specific internal reason code (`execute_purge_caller_not_allowed`, and so on). Refusals are
part of the audit trail, not just an error to the caller.

## Tenant and region scope

Beyond the caller allow-list, every scoped document read compares the caller's declared tenant and
region against the document's:

| condition | outcome |
|---|---|
| caller has no tenant or region | denied, `caller_scope_mismatch` |
| the document has no tenant or region | unavailable, `document_scope_unavailable` |
| tenant differs, or region differs (case-insensitively) | denied, `caller_scope_mismatch` |
| the document has been purged | unavailable, `document_purged` |
| otherwise | allowed |

This is applied on the shared path behind metadata, download and the other scoped reads, so it
cannot be bypassed by choosing a different endpoint. The batch preflight uses the same decision
function, which is why its answers agree with the routes that enforce them.

Note the second row: a document stored without a tenant is unreadable by every caller, permanently
— see [#93](https://github.com/sgajbi/lotus-archive/issues/93).

The response does not distinguish "not permitted" from "wrong tenant", so the error contract cannot
be used to discover which documents exist in another tenant.

## What is recorded

Sixteen event types cover every archive action, plus a seventeenth for refusals:

`archive_create` · `metadata_read` · `binary_download` · `access_events_read` · `retention_read` ·
`purge_evaluation` · `purge_execution` · `legal_hold_set` · `legal_hold_release` ·
`lifecycle_supersede` · `lifecycle_correct` · `lifecycle_reissue` · `current_document_read` ·
`source_events_read` · `batch_access_preflight` · `idea_lifecycle_decision_read` ·
`authorization_denied`

Each event carries the actor type and id, the calling service, the authorization decision and its
stable reason code, an operation reason code where one applies, the document id where the event is
tied to one, and the correlation and trace identifiers. Reason codes are stable strings, so an audit
query is written against a vocabulary rather than against prose.

`GET /documents/{document_id}/access-events` returns them for a document.

**Access audit is currently in-memory and does not survive a restart** — `InMemoryAccessAuditRepository`
is the only implementation. For a service whose purpose includes access audit, that is the most
consequential open gap: see [#90](https://github.com/sgajbi/lotus-archive/issues/90).

## Integrity of what is stored

Every document is hashed with SHA-256 at write, and the algorithm is pinned — the metadata model
rejects any `checksum_algorithm` other than `sha256`. The checksum is verified again on download; a
mismatch is `409 document_checksum_mismatch` rather than a silent return of altered bytes.

`archive_request_id` idempotency prevents the same generated document being archived twice under
different identifiers, and prevents an identifier being rebound to different content.

Together these mean a document's identity is provable independently of the storage layer: the
checksum ties the bytes to the record, and the record ties them to the render and report that
produced them.

## What responses never contain

Support-safe construction throughout. No response returns raw report payloads, storage paths,
storage keys, or raw client references. Source events additionally omit document bytes and raw
lifecycle reason text. Structured request logs record the **route template** rather than the
resolved path, so document identifiers do not reach log aggregation.

The batch preflight is explicit about this: it returns access states only, never storage truth.

## Request bounds

Document content arrives base64-encoded and is bounded **before decoding** at
`LOTUS_ARCHIVE_MAX_DECODED_DOCUMENT_BYTES` (10 MiB default), with the encoded-character ceiling
derived from it. An oversized document is refused without being expanded in memory first.

## Secrets

One secret exists: `LOTUS_ARCHIVE_IDEA_LIFECYCLE_DECISION_PRIVATE_KEY_BASE64`, the Ed25519 signing
key for Idea lifecycle decision projections. It is held as a `SecretStr`, validated as base64 and
required to be exactly 32 bytes.

A non-local profile additionally refuses to start unless a real key is present **and** the signing
key id is not an `ephemeral-local` one — so a production profile cannot run on the development key.
Note that this validation is unreachable today for a different reason: no production profile can
start at all ([#90](https://github.com/sgajbi/lotus-archive/issues/90)).

Managed key custody, rotation and consumer trust distribution remain open
([#55](https://github.com/sgajbi/lotus-archive/issues/55)). Treat the signing capability as
uncertified.

## Supply chain

`make security-audit` runs on every CI lane. Release images contain only the application wheel and
declared runtime dependencies; the package installer is removed after installation so vendored
dependency metadata cannot pollute the runtime SBOM.

**Both pull requests and mainline block on any fixable CRITICAL or HIGH vulnerability**, with
identical severity and `ignore-unfixed` settings in each lane — so a pull request cannot pass a bar
the release lane would fail. The pull-request Docker job scans the image it builds, so a vulnerable
image is rejected in review rather than after merge; mainline additionally blocks image signing and
attestation.

`GET /version` publishes the provenance chain — commit, ref, build timestamp, CI run, image
reference, image digest and digest posture. Production deployment certification remains blocked
until deployment manifests consume that digest and same-digest promotion evidence exists.

## Read next

1. [API Surface](API-Surface) — the operations these controls apply to
2. [Document Lifecycle](Document-Lifecycle) — what a purge and a legal hold actually do
3. [Configuration](Configuration) — the settings behind the fail-closed rules
