# Glossary

The vocabulary `lotus-archive` uses, with the page that defines each term authoritatively. Terms are
defined once elsewhere and summarised here for navigation — where the two differ, follow the link.

## Documents

| term | meaning | defined in |
|---|---|---|
| **generated document** | a report artefact produced by the Lotus platform — the only thing this service accepts. Not a file, not an upload. | [Home](Home#what-it-accepts) |
| **`document_id`** | the archive's identifier for a stored document | [API Surface](API-Surface) |
| **`archive_request_id`** | the caller's idempotency key; reuse with different content is a conflict | [API Surface](API-Surface#idempotency) |
| **report type** | one of four governed types — `portfolio_review`, `outcome_review`, `proof_pack`, `rebalance_wave` | [Home](Home#what-it-accepts) |
| **classification** | the document's sensitivity: `internal`, `confidential`, `restricted` | [API Surface](API-Surface#the-archive-contract) |
| **checksum** | SHA-256 over the stored bytes, computed at write and verified at download. The algorithm is pinned. | [Security and Controls](Security-and-Controls#integrity-of-what-is-stored) |

## Lifecycle

| term | meaning | defined in |
|---|---|---|
| **retention** | how long a document must be kept. Supplied by the caller, enforced here, never computed here. | [Document Lifecycle](Document-Lifecycle#retention) |
| **`retain_until_date`** | the date after which purge becomes possible. Its absence means *never purgeable*. | [Document Lifecycle](Document-Lifecycle#purge) |
| **legal hold** | a named, authority-referenced block on destruction. Multiple holds may apply; the last release clears the block. | [Document Lifecycle](Document-Lifecycle#legal-hold) |
| **purge** | destruction of the bytes. The metadata record survives, stamped `purged`. | [Document Lifecycle](Document-Lifecycle#purge) |
| **purge eligibility** | the ordered decision — purged, held, no retention date, retention running, or elapsed | [Document Lifecycle](Document-Lifecycle#purge) |
| **supersede** | a newer document replaces this one; the earlier is no longer current | [Document Lifecycle](Document-Lifecycle#correction-supersession-and-reissue) |
| **correct** | the earlier document was wrong. A stronger assertion than supersede. | [Document Lifecycle](Document-Lifecycle#correction-supersession-and-reissue) |
| **reissue** | the same content issued again; nothing about the content changed | [Document Lifecycle](Document-Lifecycle#correction-supersession-and-reissue) |
| **current document** | the end of a supersession chain — what the client has now | [Document Lifecycle](Document-Lifecycle#resolving-the-current-document) |
| **source events** | the bounded, pull-only lifecycle projection for portfolio-memory consumers | [Document Lifecycle](Document-Lifecycle#source-events) |

## Access

| term | meaning | defined in |
|---|---|---|
| **caller context** | the self-declared identity headers: caller service, actor type, actor id | [Security and Controls](Security-and-Controls#the-controlling-fact-caller-identity-is-self-declared) |
| **caller scope** | the tenant and region headers required on scoped document reads | [Security and Controls](Security-and-Controls#tenant-and-region-scope) |
| **permission** | one of eleven named capabilities, each with a fixed list of permitted caller services | [Security and Controls](Security-and-Controls#who-may-call-what) |
| **access event** | the audit record written for every archive action, including refusals | [Security and Controls](Security-and-Controls#what-is-recorded) |
| **access preflight** | the batch, advisory answer to "would this caller be allowed these documents" | [API Surface](API-Surface#batch-access-preflight) |
| **support-safe** | a response or log constructed so that operating the service does not require access to client data or storage truth | [Security and Controls](Security-and-Controls#what-responses-never-contain) |

## Runtime

| term | meaning | defined in |
|---|---|---|
| **runtime profile** | `local-development`, `test` or `production` — the posture the settings validator enforces against | [Configuration](Configuration#runtime-composition) |
| **repository mode / storage mode** | which adapters to compose: local `in-memory`/`filesystem`, or production `postgresql`/`s3` | [Configuration](Configuration#what-can-actually-run) |
| **runtime posture** | the composed state reported by `/health/ready` and `/metadata`: `ready`, `degraded` or `unavailable` | [Operations](Operations#readiness) |
| **supportability posture** | the `/metadata` capability block derived from drain state and measured repository, storage, and access-audit readiness | [Operations](Operations#measured-supportability) |
| **module family** | one of the seven structural boundaries the architecture tests enforce | [Architecture](Architecture#module-families) |

## Scope words that carry weight

| term | meaning |
|---|---|
| **client-publication authority** | the upstream right to treat a document as client-ready. Archiving never grants it; Idea evidence is archived with it withheld. |
| **advisor-use** | content approved for an advisor to read, not for a client. Archiving preserves the posture and does not promote it. |
| **not certified** | implemented and working, but without the key custody, durable persistence, trust distribution and approvals that would make it something to rely on — currently the Idea lifecycle decision boundary. |
| **projection** | a read-only statement of archive state issued to a consumer. Never an instruction, and never an authorisation to destroy anything. |

## Read next

1. [Home](Home) — what the service is for
2. [Document Lifecycle](Document-Lifecycle) — where most of this vocabulary is defined
3. [API Surface](API-Surface) — the operations the terms describe
