# Analytics Schemas

## 0.4 structural analysis

The analysis database uses application ID `1346654808` and remains separate from inventory and
decision databases.

- `analysis_runs` binds one run to an inventory path, scan session, and logical input digest.
- `analysis_stages` records `roles`, `directory_aggregates`, `projects`, and `relationships`.
- `item_roles` stores deterministic role, confidence, rule ID, explanation, and evidence JSON.
- `directory_aggregates` stores recursive bytes/counts, role counts, and role coherence.
- `projects` stores boundary score, marker evidence, and rule version.
- `relationships` stores structural project evidence such as nested projects and observed roles.

Every output table is keyed by run ID. Consumers must require both the run and all required stages
to be `COMPLETE` and must match the recorded inventory input digest.

## 0.5 Pareto review ranking

The ranking database uses application ID `1346654809`, is created as a new file beside the
analysis database, and records the selected complete analysis run and logical input digest.

- `ranking_runs` records state, output digest, and exact DuckDB/Polars/PyArrow versions.
- `ranking_stages` records `materialize`, `objectives`, `pareto`, and `review` provenance.
- `directory_features` stores the bounded analytical feature set and explicit cohort.
- `objective_intervals` keeps each objective's low, point, high, and confidence independently.
- `pareto_results` stores cohort-local robust non-dominated rank.
- `review_queue` stores a bounded question priority and explanation; it is not an action plan.

The 0.5 reader opens 0.4 in SQLite read-only/query-only mode. It never opens the inventory or
observed source paths, and none of its outputs authorize filesystem changes.

## 0.6 proposal optimization

The plans database uses application ID `1346654810` and binds a complete ranking run to a
query-only decision snapshot and explicit capacity policy.

- `plan_runs` records ranking, decision/session digests, configuration, dependencies, and state.
- `plan_stages` records `candidates`, `exact`, `nsga3`, `rnsga3`, `validate`, and `present`.
- `candidate_groups` stores the hierarchy and explicit eligibility/protection constraints.
- `proposed_plans` stores independently recomputed objectives and `UNAPPROVED` state.
- `plan_actions` stores one action for every candidate in every retained plan.
- `proposed_archives` stores collision-checked proposal names; no archive is created.

The plans database is a proposal artifact, not an approval manifest and not executor input.

## 0.7 content enrichment

The evidence database uses application ID `1346654811`, is a new file beside the inventory, and
binds an explicit selection manifest to a complete inventory snapshot and its source-volume
identity.

- `enrichment_runs` records the selection, policy, BLAKE3 version, byte counts, and terminal state.
- `enrichment_stages` records `selection`, `read`, and `duplicates` provenance.
- `file_evidence` stores per-file evidence level, algorithm, digest, size, and bytes read.
- `duplicate_groups` and `duplicate_members` store D2 `CANDIDATE` or D3/D4 `CONFIRMED` groups.
- `enrichment_errors` records fail-closed run errors.

Evidence is not an approval, plan, archive manifest, or executor input.

## 0.8 plan-selection approval artifacts

Stage 0.8 creates canonical JSON rather than another mutable database. A strict declaration binds
an operator label, timestamp, acknowledgement set, complete plan run, selected plan ID, plan
output digest, and decision digest. The resulting receipt includes independently recomputed
objectives and actions plus a logical digest over the consumed plan records.

The receipt state is `PLAN_SELECTED_FOR_FUTURE_EXECUTOR_REVIEW`. Its execution, archive-creation,
and original-removal authorizations are all `false`; it is not executor input.

## 0.9 executor-preflight manifest

Stage 0.9 creates a canonical JSON member manifest after tracing the selected plan through the
recorded ranking and analysis runs to a complete inventory session. Each proposed archive group
contains its reconciled regular-file observations: relative path, logical bytes, creation and
modification times, and attributes.

The manifest state is `PREFLIGHT_ONLY_NON_EXECUTABLE`. Source-content-read, execution,
archive-creation, and original-removal authorizations are all `false`.

## 0.10 enrichment-evidence fusion

The fusion database uses application ID `1346654812` and binds one complete structural analysis
run to one complete enrichment run over the same inventory session and logical digest.

- `fusion_runs` records both inputs, evidence level, counts, digests, and state.
- `fusion_stages` records `validate`, `import`, and `directory_features` provenance.
- `imported_file_evidence` preserves the per-file algorithm and digest.
- `imported_duplicate_groups` and `imported_duplicate_members` preserve candidate/confirmed status.
- `directory_evidence_features` stores selection coverage and separate D2 versus D3/D4 member
  counts and bytes.

The fusion database is analytical evidence, not an approval or executor input.
