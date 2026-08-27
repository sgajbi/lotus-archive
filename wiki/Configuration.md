# Configuration

Every setting `lotus-archive` reads, and — more importantly — which combinations of them actually
produce a running service. Taken from
[`src/app/archive/settings.py`](https://github.com/sgajbi/lotus-archive/blob/main/src/app/archive/settings.py)
and [`runtime.py`](https://github.com/sgajbi/lotus-archive/blob/main/src/app/archive/runtime.py) on
`main`.

All variables take the **`LOTUS_ARCHIVE_`** prefix. Unknown variables are ignored; invalid ones fail
at settings load rather than degrading the service.

## What can actually run

Read this before the tables. Two independent validations decide whether the service starts, and they
accept **disjoint** sets of configurations:

| | `runtime_profile` | `repository_mode` | `storage_mode` | result |
|---|---|---|---|---|
| settings validator | `production` | `in-memory` | any | **rejected** — in-memory requires a local profile |
| settings validator | `production` | any | `filesystem` | **rejected** — filesystem requires a local profile |
| runtime composer | any | not `in-memory` | any | **rejected** — the PostgreSQL adapter does not exist |
| runtime composer | any | any | not `filesystem` | **rejected** — the S3 adapter does not exist |

The only configuration that survives both is `local-development` or `test`, with `in-memory` and
`filesystem`. **There is no production configuration that starts.** This is a delivery gap, not a
deployment task — tracked as [#90](https://github.com/sgajbi/lotus-archive/issues/90).

Two consequences in the configuration that does run:

- archived bytes live under `storage_root`, which defaults to a path in the **OS temp directory**
- access audit records are in-memory and **do not survive a restart**

The runtime posture reported by `/health/ready` and `/metadata` reflects this honestly: it is
`degraded` with reason `explicit_local_development_runtime`, and it can never be `ready`, because
`ready` requires the durable adapters that cannot be built.

## Runtime composition

| variable | default | values |
|---|---|---|
| `LOTUS_ARCHIVE_RUNTIME_PROFILE` | `local-development` | `local-development`, `test`, `production` |
| `LOTUS_ARCHIVE_REPOSITORY_MODE` | `in-memory` | `in-memory`, `postgresql` |
| `LOTUS_ARCHIVE_STORAGE_MODE` | `filesystem` | `filesystem`, `s3` |
| `LOTUS_ARCHIVE_DATABASE_URL` | *(unset)* | required when `repository_mode=postgresql` |

The validator enforces three rules, all fail-closed in the direction of refusing to run rather than
running non-durably:

1. a non-local profile may not use the in-memory repository
2. a non-local profile may not use filesystem storage
3. `postgresql` without a database URL is rejected

The intent is sound — nothing silently publishes non-durable archive state. The gap is that the
durable side of each rule is not implemented.

## Storage

| variable | default | notes |
|---|---|---|
| `LOTUS_ARCHIVE_STORAGE_ROOT` | `<temp dir>/lotus-archive-objects` | filesystem storage location |
| `LOTUS_ARCHIVE_STORAGE_NAMESPACE` | `local-development` | prefixes stored objects; minimum length 1 |

Objects are laid out as `region / tenant / report-type / document-id.format`. A document archived
without a tenant is filed under `tenant-unspecified` — a storage-layout fallback that does **not**
populate the metadata, which is why such a document is unreadable
([#93](https://github.com/sgajbi/lotus-archive/issues/93)).

## Document bounds

| variable | default | notes |
|---|---|---|
| `LOTUS_ARCHIVE_MAX_DECODED_DOCUMENT_BYTES` | `10485760` (10 MiB) | minimum 1 |

The encoded-character ceiling is derived from this value, so an oversized base64 body is rejected
before it is decoded rather than after.

## Idea lifecycle decision signing

| variable | default | notes |
|---|---|---|
| `LOTUS_ARCHIVE_IDEA_LIFECYCLE_DECISION_LEDGER_PATH` | `<temp dir>/lotus-archive-idea-lifecycle-decisions.sqlite3` | local SQLite replay ledger |
| `LOTUS_ARCHIVE_IDEA_LIFECYCLE_DECISION_PRIVATE_KEY_BASE64` | *(empty)* | Ed25519 private key, exactly 32 bytes, base64 |
| `LOTUS_ARCHIVE_IDEA_LIFECYCLE_DECISION_SIGNING_KEY_ID` | `ephemeral-local-v1` | minimum length 3 |

Validation is layered. A supplied key must decode as base64 and be exactly 32 bytes, in every
profile. A non-local profile additionally requires that a key is present *and* that the signing key
id does not begin with `ephemeral-local` — so a production deployment cannot run on the development
key or an unnamed one.

The ledger defaults to the temp directory, so replay protection is not durable in the runnable
configuration either. The capability is not certified — see
[#55](https://github.com/sgajbi/lotus-archive/issues/55) and
[Document Lifecycle](./Document-Lifecycle.md#idea-lifecycle-decisions).

## Deployment

There is no deployable production configuration today, so this section records what a deployment
would need rather than describing one that exists:

1. a PostgreSQL repository adapter and an S3 storage adapter (neither is implemented)
2. a durable access-audit repository — the only implementation is in-memory, and durability is
   currently *inferred* from `repository_mode` rather than measured
   ([#91](https://github.com/sgajbi/lotus-archive/issues/91))
3. managed Ed25519 key material with a non-ephemeral key id
4. deployment manifests that consume the image digest published by `GET /version`, plus same-digest
   promotion evidence

Container images are built and scanned in CI today, and provenance is published through
`/version`; what is missing is the runtime the image would run as.

## Read next

1. [Architecture](./Architecture.md) — what each adapter is and where it plugs in
2. [Operations](./Operations.md) — how the posture surfaces report all of this
3. [Security and Controls](./Security-and-Controls.md) — the secret and its validation
