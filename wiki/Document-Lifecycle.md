# Document Lifecycle

What happens to a generated document between the moment it is archived and the moment it is
destroyed — and the rules that decide whether that moment ever arrives. This is the business
behaviour of the service; the endpoints that expose it are in [API Surface](API-Surface).

## The one-way rules

Three properties hold across everything below, and most of the design follows from them:

1. **A document is never edited.** Correcting what a client was told creates a *new* document and
   records a relationship to the old one. The original stays retrievable.
2. **Destruction removes bytes, not the record.** After a purge the metadata survives — document
   identity, checksum, lineage, retention posture and purge timestamp all remain. The archive can
   still prove what existed and that it was destroyed under policy.
3. **Absence of a retention date means never.** A document with no `retain_until_date` is not
   purgeable, in perpetuity. The service fails closed toward keeping.

## Retention

Retention is **supplied, not computed**. `lotus-report` sends `retention_policy_id`,
`retention_start_date` and `retain_until_date` on the archive request; `lotus-archive` enforces what
it is given and has no policy engine of its own. All three fields are optional, and validation only
checks that `retention_start_date` is not after `retain_until_date`.

`GET /documents/{document_id}/retention` returns the current posture. The posture is derived on
read rather than stored as a schedule, so it always reflects today's date and the current hold
state.

## Legal hold

A legal hold is an explicit, named block on destruction. `POST /documents/{document_id}/legal-holds`
sets one with an authority reference; `DELETE .../legal-holds/{legal_hold_id}` releases it. Holds
are records, not flags — a document carries a `legal_hold_count` and a `legal_hold_status` of
`clear` or `active`, refreshed from the underlying hold records on every lifecycle read.

Releasing a hold is idempotent: releasing one that is already released changes nothing and does not
error. Setting a second hold while one is active is not a conflict — a document can be held by more
than one matter, and it stays held until the last one is released.

## Purge

Purge evaluation runs the same five checks in the same order for both
`POST /documents/{document_id}/purge-evaluation` and `POST /documents/{document_id}/purge`. The
order is the business rule:

| # | condition | eligible | reason code |
|---|---|---|---|
| 1 | already purged | yes | `already_purged` |
| 2 | a legal hold is active | **no** | `legal_hold_active` |
| 3 | no `retain_until_date` | **no** | `retain_until_date_missing` |
| 4 | `retain_until_date` is in the future | **no** | `retention_period_active` |
| 5 | otherwise | yes | `retention_elapsed` |

Legal hold is checked **before** retention, so a held document is reported as held rather than as
retained — the operator learns the actionable reason, not the incidental one. Retention is evaluated
against the server's current date; callers cannot supply an evaluation date through the API.

Evaluation is not read-only: it writes back the `purge_status` it computed (`eligible` or
`not_eligible`), so the stored posture stays consistent with the answer just given.

Execution then:

1. deletes the object from storage
2. sets `purge_status = purged` and stamps `purged_at`
3. records a purge-execution access event

A blocked purge is recorded too, with its reason code, before the error is raised — a refused
destruction attempt is itself evidence. An active hold raises `legal_hold_active`; any other
ineligibility raises a purge-not-eligible error.

After purge the document remains addressable, but reads are denied at the scope check with
`document_purged` rather than returning bytes that no longer exist.

## Correction, supersession and reissue

Three lifecycle transitions, all append-only, all creating a relationship record rather than
mutating history:

| transition | meaning | when to use |
|---|---|---|
| `supersede` | a newer document replaces an older one | the content has moved on — a later period, a restated position |
| `correct` | the earlier document was wrong | the client was told something incorrect and needs the corrected version |
| `reissue` | the same content, issued again | redelivery, a new copy for a new recipient; nothing about the content changed |

The distinction is not cosmetic. `correct` asserts the earlier document was defective, which is a
different statement to a regulator than `supersede`, which asserts only that it is no longer
current. `reissue` asserts neither.

Each transition writes both directions — the old document gains `superseded_by_document_id`, the new
one gains `supersedes_document_id` (or `correction_of_document_id` / `reissue_of_document_id`) — so
the chain can be walked from either end.

### What the transitions refuse

Five guards keep the relationship graph a set of clean linear chains rather than a web:

| refused | error |
|---|---|
| a document transitioning to itself | unsupported transition |
| either side already purged | unsupported transition |
| the source already superseded — it is history, not the current document | supersession conflict |
| the target already superseded | supersession conflict |
| the target already having a lifecycle origin | supersession conflict |

The last guard is the one worth understanding: a new document may originate from at most one
predecessor. Chains are allowed — a correction may itself later be corrected — but a document cannot
be given two successors, so "which document replaced this one" always has a single answer.

Note that all three transition types mark the source as superseded. The type is recorded in the
relationship and in the direction-specific field on the new document; it does not change the fact
that the earlier document is no longer current.

### Resolving the current document

`GET /documents/{document_id}/current` walks the supersession chain from any document in it and
returns the one nothing has superseded. The walk tracks visited identifiers and raises a
supersession-conflict error if it revisits one, so a relationship cycle surfaces as an explicit
failure rather than a hang.

This is the endpoint to ask *"what does the client have now?"* from any historical document id.

## Source events

`GET /documents/{document_id}/source-events` projects archive-owned lifecycle facts for downstream
consumers — principally portfolio memory — as a pull-only, bounded (`limit`/`offset`) replay with
stable reason codes.

Events carry document identity, report-input provenance, and codes such as
`archive_metadata_persisted`, `generated_document_checksum_preserved` and the summary-preservation
codes for reviewed narrative, advisor memo and Idea evidence. They carry **no** document bytes, no
storage keys, no raw report payloads, no raw lifecycle reason text and no raw client references.

The contract lets a consumer cite archive evidence without treating the archive as an authority on
transactions, positions, calculations or methodology — which it is not.

## How each report type arrives

Every document reaches the archive the same way — `lotus-report` submits it after `lotus-render`
returns a compiled artefact — but the upstream authority differs by type:

| report type | upstream authority | notable constraint |
|---|---|---|
| `portfolio_review` | `lotus-report` over core, performance and risk data | may carry a reviewed advisory narrative or advisor proposal memo summary from `lotus-advise`, advisor-use only |
| `outcome_review` | `lotus-manage` | post-trade outcome truth stays with Manage; archive presents and retains |
| `proof_pack` | `lotus-manage`, or `lotus-idea` for reviewed Idea evidence | Idea evidence is archived with `client_publication_authority_granted=false` |
| `rebalance_wave` | `lotus-manage` | wave state and proof-pack linkage stay with Manage |

Validation binds each optional summary to its report type and template: a reviewed advisory
narrative or advisor memo is accepted only on a `portfolio_review` using the `portfolio-review`
template, and an Idea evidence pack only on a `proof_pack` using the `proof-pack` template with
`dpm_proof_pack_report_input.v1`. A mismatched combination is rejected rather than stored.

## Idea lifecycle decisions

`POST /documents/{document_id}/idea-lifecycle-decisions` issues a tenant-bound, short-lived
Ed25519-signed projection of archive retention, hold and purge posture for Idea-linked proof-pack
evidence, with durable local replay protection.

Two boundaries are load-bearing: the decision is a **projection of archive state, not an
instruction**, and it **never authorises disposal**. `lotus-idea` cannot set or release a hold and
cannot cause a purge.

The capability is **not certified**. Managed signing keys, durable production persistence, consumer
trust distribution, legal approval and live evidence all remain open — see
[#55](https://github.com/sgajbi/lotus-archive/issues/55). Treat it as a working boundary, not a
control anyone should yet rely on.

## Read next

1. [API Surface](API-Surface) — the operations that expose all of the above
2. [Security and Controls](Security-and-Controls) — who may invoke them, and what is recorded
3. [Glossary](Glossary) — the vocabulary
