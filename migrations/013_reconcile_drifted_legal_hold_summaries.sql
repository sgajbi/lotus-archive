-- 013: reconcile legal-hold summaries that drifted before recounts became
-- derived-in-transaction (issue #166).
--
-- The historic race let a stale recount overwrite a newer hold's summary with
-- CLEAR/0, and let a release path publish a count taken before a concurrent
-- admission committed. Rows written under that defect can therefore disagree
-- with their hold rows in either direction. Destruction is already refused for
-- an active hold ROW by the NOT EXISTS belts in begin_purge and
-- mark_purge_eligible; this repair makes the stored summary agree with the
-- hold rows so reads stop disagreeing with them.
--
-- Idempotent: the derivation is a pure function of the hold rows, and the
-- change predicate updates nothing when the summary already agrees, so a
-- re-run converges without churning updated_at.
--
-- Deliberately NOT healed here: purge state erased by the old whole-row
-- lifecycle save is unrecoverable from remaining metadata alone (a reverted
-- purge is indistinguishable from a never-purged row without consulting the
-- object store), so no purge column is rewritten by this repair.
UPDATE archive_documents AS d
SET legal_hold_status = derived.derived_status,
    legal_hold_count = derived.derived_count,
    updated_at = now()
FROM (
    SELECT
        documents.document_id,
        CASE
            WHEN count(holds.legal_hold_id) FILTER (WHERE holds.hold_status = 'active') > 0
            THEN 'active'
            ELSE 'clear'
        END AS derived_status,
        (count(holds.legal_hold_id) FILTER (WHERE holds.hold_status = 'active'))::int
            AS derived_count
    FROM archive_documents AS documents
    LEFT JOIN archive_legal_holds AS holds
        ON holds.document_id = documents.document_id
    GROUP BY documents.document_id
) AS derived
WHERE derived.document_id = d.document_id
  AND (d.legal_hold_status IS DISTINCT FROM derived.derived_status
       OR d.legal_hold_count IS DISTINCT FROM derived.derived_count);
