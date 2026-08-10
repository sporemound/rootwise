# 0.8 Non-Executing Plan-Approval Contract

The original Rootwise roadmap did not define a 0.8 milestone. This stage is the smallest bridge
between proposal-only optimization and a possible future executor preview: it records which
validated proposal a person selected, while deliberately withholding every filesystem-action
authorization.

## Declaration

The operator creates UTF-8 JSON with exactly these fields:

```json
{
  "schema_version": "rootwise-plan-approval-declaration-1",
  "plan_run_id": "complete-plan-run-id",
  "plan_id": "64-lowercase-hex-characters",
  "plan_output_digest": "64-lowercase-hex-characters",
  "decisions_digest": "64-lowercase-hex-characters",
  "intent": "SELECT_PLAN_FOR_FUTURE_EXECUTOR_REVIEW",
  "acknowledgements": [
    "ARCHIVE_CREATION_REQUIRES_A_SEPARATE_EXECUTOR",
    "ORIGINAL_REMOVAL_REQUIRES_A_LATER_SEPARATE_REVIEW"
  ],
  "operator": "operator-chosen-label",
  "approved_at": "2026-08-09T22:00:00Z",
  "note": "Reason for selecting this proposal."
}
```

The field set and acknowledgement order are exact. The timestamp must include a UTC offset. The
operator label is an audit label only: Stage 0.8 does not authenticate identity, provide a digital
signature, or establish non-repudiation.

## Validation and receipt

The plans database is opened SQLite read-only/query-only and held in a read transaction. The
declared run must be `COMPLETE`, its required stages must be consumable, and its output and decision
digests must match the declaration. The selected proposal must still be validated and
`UNAPPROVED` in the immutable 0.6 plans database.

Stage 0.8 reloads the bounded candidate set, capacity policy, action for every candidate,
objectives, and proposed archive labels. It independently invokes the deterministic 0.6 plan
validator to recheck candidate identity, hierarchy, eligibility, protection, capacity, objectives,
plan ID, and label uniqueness. Any mismatch aborts before a receipt is created.

The canonical receipt records the declaration digest, consumed plan-record digest, policy,
objectives, and every directory-level action. Its `receipt_digest` is SHA-256 over the canonical
receipt before that digest field is inserted.

## Explicit non-authorizations

Every receipt contains:

```json
{
  "execution_authorized": false,
  "archive_creation_authorized": false,
  "original_removal_authorized": false
}
```

Directory actions are not an enumerated archive-member manifest. A future separately distributed
component would still need an approved immutable member list, current source-observation
revalidation, destination-capacity validation, archive transaction safety, and post-write
verification. Stage 0.8 never opens the inventory, enrichment evidence, or observed source paths
and contains no archive, copy, move, rename, delete, network, shell, or subprocess capability.
