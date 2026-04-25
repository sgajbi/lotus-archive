# Supported Features

This document records implementation-backed support posture for `lotus-archive`.

## Current State

`lotus-archive` currently supports only the governed service boundary scaffold:

1. FastAPI application shell.
2. Health, liveness, readiness, metadata, metrics, correlation headers, and trace headers.
3. Repository-native quality gates and CI baseline.
4. Archive-specific module-family and documentation structure.
5. Safe error envelope for service-level errors.
6. Caller-context parsing helper for future protected archive APIs.
7. Structured support-safe request logging.

No client-facing archive product feature is supported yet.

## Not Yet Supported

| Capability | Support state | Reason |
| --- | --- | --- |
| Generated-document archival | `not_supported` | Metadata and storage APIs are not implemented yet. |
| Controlled document metadata lookup | `not_supported` | Archive metadata API is not implemented yet. |
| Controlled document download or signed URL issuance | `not_supported` | Retrieval API and authorization posture are not implemented yet. |
| Access audit for document retrieval | `not_supported` | Access-audit model is not implemented yet. |
| Retention policy assignment and purge eligibility | `not_supported` | Retention model is not implemented yet. |
| Legal hold set/release with purge blocking | `not_supported` | Legal-hold model and APIs are not implemented yet. |
| Supersession, correction, and reissue relationships | `not_supported` | Lifecycle relationship model is not implemented yet. |
| Report-to-archive handoff | `not_supported` | `lotus-report` integration is not implemented yet. |
| Gateway-backed document retrieval | `not_supported` | Gateway facade is not implemented yet. |
| Workbench document retrieval surface | `not_supported` | Product surface is not implemented and must remain gateway-backed if added. |
| Arbitrary file storage | `not_supported` | Out of RFC-0103 scope. |
| Manual customer document upload | `not_supported` | Out of RFC-0103 first-wave scope. |

## Update Rule

Add a capability here only after the backing code, tests, documentation, and PR evidence exist. Do
not describe infrastructure as a client-supported retrieval feature.
