# Glossary

The vocabulary `lotus-archive` uses, with the page that defines each term authoritatively. Terms are
defined once elsewhere and summarised here for navigation — where the two differ, follow the link.

## Documents

| term | meaning | defined in |
|---|---|---|
| **generated document** | a report artefact produced by the Lotus platform — the only thing this service accepts. Not a file, not an upload. | [Home](./Home.md#what-it-accepts) |
| **`document_id`** | the archive's identifier for a stored document | [API Surface](./API-Surface.md) |
| **`archive_request_id`** | the caller's idempotency key; reuse with different content is a conflict | [API Surface](./API-Surface.md#idempotency) |
| **report type** | one of four governed types — `portfolio_review`, `outcome_review`, `proof_pack`, `rebalance_wave` | [Home](./Home.md#what-it-accepts) |
| **classification** | the document's sensitivity: `internal`, `confidential`, `restricted` | [API Surface](./API-Surface.md#the-archive-contract) |
| **checksum** | SHA-256 over the stored bytes, computed at write and verified at download. The algorithm is pinned. | [Security and Controls](./Security-and-Controls.md#integrity-of-what-is-stored) |

## Lifecycle

| term | meaning | defined in |
|---|---|---|
| **retention** | how long a document must be kept. Supplied by the caller, enforced here, never computed here. | [Document Lifecycle](./Document-Lifecycle.md#retention) |
| **`retain_until_date`** | the date after which purge becomes possible. Its absence means *never purgeable*. | [Document Lifecycle](./Document-Lifecycle.md#purge) |
| **legal hold** | a named, authority-referenced block on destruction. Multiple holds may apply; the last release clears the block. | [Document Lifecycle](./Document-Lifecycle.md#legal-hold) |
| **purge** | destruction of the bytes. The metadata record survives, stamped `purged`. | [Document Lifecycle](./Document-Lifecycle.md#purge) |
| **purge eligibility** | the ordered decision — purged, held, no retention date, retention running, or elapsed | [Document Lifecycle](./Document-Lifecycle.md#purge) |
| **supersede** | a newer document replaces this one; the earlier is no longer current | [Document Lifecycle](./Document-Lifecycle.md#correction-supersession-and-reissue) |
| **correct** | the earlier document was wrong. A stronger assertion than supersede. | [Document Lifecycle](./Document-Lifecycle.md#correction-supersession-and-reissue) |
| **reissue** | the same content issued again; nothing about the content changed | [Document Lifecycle](./Document-Lifecycle.md#correction-supersession-and-reissue) |
| **current document** | the end of a supersession chain — what the client has now | [Document Lifecycle](./Document-Lifecycle.md#resolving-the-current-document) |
| **source events** | the bounded, pull-only lifecycle projection for portfolio-memory consumers | [Document Lifecycle](./Document-Lifecycle.md#source-events) |

## Access

| term | meaning | defined in |
|---|---|---|
| **caller context** | the self-declared identity headers: caller service, actor type, actor id | [Security and Controls](./Security-and-Controls.md#the-controlling-fact-caller-identity-is-self-declared) |
| **caller scope** | the tenant and region headers required on scoped document reads | [Security and Controls](./Security-and-Controls.md#tenant-and-region-scope) |
| **permission** | one of eleven named capabilities, each with a fixed list of permitted caller services | [Security and Controls](./Security-and-Controls.md#who-may-call-what) |
| **access event** | the audit record written for every archive action, including refusals | [Security and Controls](./Security-and-Controls.md#what-is-recorded) |
| **access preflight** | the batch, advisory answer to "would this caller be allowed these documents" | [API Surface](./API-Surface.md#batch-access-preflight) |
| **support-safe** | a response or log constructed so that operating the service does not require access to client data or storage truth | [Security and Controls](./Security-and-Controls.md#what-responses-never-contain) |

## Runtime

| term | meaning | defined in |
|---|---|---|
| **runtime profile** | `local-development`, `test` or `production` — the posture the settings validator enforces against | [Configuration](./Configuration.md#runtime-composition) |
| **repository mode / storage mode** | which adapters to compose. Only `in-memory` and `filesystem` are implemented. | [Configuration](./Configuration.md#what-can-actually-run) |
| **runtime posture** | the composed state reported by `/health/ready` and `/metadata`: `ready`, `degraded` or `unavailable` | [Operations](./Operations.md#readiness) |
| **supportability posture** | the `/metadata` capability block. A static declaration, not a measurement. | [Operations](./Operations.md#supportability-is-declared-not-measured) |
| **module family** | one of the seven structural boundaries the architecture tests enforce | [Architecture](./Architecture.md#module-families) |

## Scope words that carry weight

| term | meaning |
|---|---|
| **client-publication authority** | the upstream right to treat a document as client-ready. Archiving never grants it; Idea evidence is archived with it withheld. |
| **advisor-use** | content approved for an advisor to read, not for a client. Archiving preserves the posture and does not promote it. |
| **not certified** | implemented and working, but without the key custody, durable persistence, trust distribution and approvals that would make it something to rely on — currently the Idea lifecycle decision boundary. |
| **projection** | a read-only statement of archive state issued to a consumer. Never an instruction, and never an authorisation to destroy anything. |

## Read next

1. [Home](./Home.md) — what the service is for
2. [Document Lifecycle](./Document-Lifecycle.md) — where most of this vocabulary is defined
3. [API Surface](./API-Surface.md) — the operations the terms describe
