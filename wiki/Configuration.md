# Configuration

Every setting `lotus-archive` reads, and — more importantly — which combinations of them actually
produce a running service. Taken from
[`src/app/archive/settings.py`](https://github.com/sgajbi/lotus-archive/blob/main/src/app/archive/settings.py)
and [`runtime.py`](https://github.com/sgajbi/lotus-archive/blob/main/src/app/archive/runtime.py) on
`main`.

All variables take the **`LOTUS_ARCHIVE_`** prefix. Unknown variables are ignored; invalid ones fail
at settings load rather than degrading the service.

## What can actually run

Read this before the tables. Settings validation and runtime composition enforce the same posture:

| | `runtime_profile` | `repository_mode` | `storage_mode` | result |
|---|---|---|---|---|
| settings validator | `production` | `in-memory` | any | **rejected** — in-memory requires a local profile |
| settings validator | `production` | any | `filesystem` | **rejected** — filesystem requires a local profile |
| runtime composer | any | `in-memory` | `filesystem` | in-memory metadata/audit and local object storage |
| runtime composer | any | `postgresql` | `s3` | durable metadata/audit and S3-compatible object storage |

The default local profile remains deliberately non-durable:

- archived bytes live under `storage_root`, which defaults to a path in the **OS temp directory**
- access audit records are in-memory and do not survive a restart

The production combination is `production` + `postgresql` + `s3`, with a database URL, S3 bucket,
and managed lifecycle-decision signing key. It composes PostgreSQL metadata and audit repositories
plus S3-compatible object storage and reports `ready` with reason
`durable_archive_runtime_configured`. Dependency probing remains tracked by
[#91](https://github.com/sgajbi/lotus-archive/issues/91).

## Runtime composition

| variable | default | values |
|---|---|---|
| `LOTUS_ARCHIVE_RUNTIME_PROFILE` | `local-development` | `local-development`, `test`, `production` |
| `LOTUS_ARCHIVE_REPOSITORY_MODE` | `in-memory` | `in-memory`, `postgresql` |
| `LOTUS_ARCHIVE_STORAGE_MODE` | `filesystem` | `filesystem`, `s3` |
| `LOTUS_ARCHIVE_DATABASE_URL` | *(unset)* | required when `repository_mode=postgresql` |
| `LOTUS_ARCHIVE_S3_BUCKET` | *(unset)* | required when `storage_mode=s3` |
| `LOTUS_ARCHIVE_S3_KEY_PREFIX` | `archive` | prefix inside the configured bucket |
| `LOTUS_ARCHIVE_S3_REGION` | *(unset)* | AWS region or S3-compatible provider region |
| `LOTUS_ARCHIVE_S3_ENDPOINT_URL` | *(unset)* | optional S3-compatible endpoint; omit for AWS |
| `LOTUS_ARCHIVE_S3_SERVER_SIDE_ENCRYPTION` | `AES256` | `AES256` or `aws:kms` |
| `LOTUS_ARCHIVE_S3_KMS_KEY_ID` | *(unset)* | required when encryption is `aws:kms` |

The validator enforces five rules, all fail-closed in the direction of refusing to run rather than
running non-durably:

1. a non-local profile may not use the in-memory repository
2. a non-local profile may not use filesystem storage
3. `postgresql` without a database URL is rejected
4. `s3` without a bucket is rejected
5. `aws:kms` encryption without a KMS key id is rejected

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
[Document Lifecycle](Document-Lifecycle#idea-lifecycle-decisions).

## Deployment

The deployable durable composition requires:

1. all PostgreSQL migrations applied, including `007_create_archive_access_audit.sql`
2. an S3 bucket and provider credentials supplied through the standard AWS credential chain
3. managed Ed25519 key material with a non-ephemeral key id
4. dependency readiness evidence; `/metadata` probing is tracked by
   [#91](https://github.com/sgajbi/lotus-archive/issues/91)
5. deployment manifests that consume the image digest published by `GET /version`, plus same-digest
   promotion evidence

Container images are built and scanned in CI, and provenance is published through `/version`.

## Read next

1. [Architecture](Architecture) — what each adapter is and where it plugs in
2. [Operations](Operations) — how the posture surfaces report all of this
3. [Security and Controls](Security-and-Controls) — the secret and its validation
