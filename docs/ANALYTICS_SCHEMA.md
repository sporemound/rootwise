# 0.4 Analysis Schema

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
