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
