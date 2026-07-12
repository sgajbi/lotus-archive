# Idea Evidence Lifecycle Decisions

This directory owns the Archive producer contract for short-lived, authenticated lifecycle
decisions consumed by `lotus-idea` and `lotus-report`.

The decision is a source-safe projection of Archive retention, legal-hold, and purge state. It is
not a second command path: `lotus-archive` remains the only authority for hold management and purge
execution, and every decision keeps `disposal_authorized=false`.

Current contract:

1. `lotus-archive-idea-evidence-lifecycle-decision.v1.json`
   Ed25519-signed, tenant-bound, durable-idempotent local proof for archived proof-pack documents.

Production certification remains blocked until the durable Archive repository, managed Ed25519
key source and rotation process, consumer trust bundle, live runtime evidence, and legal/privacy
approval exist.
