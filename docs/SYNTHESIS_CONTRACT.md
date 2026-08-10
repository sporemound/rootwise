# 0.14 Multi-Evidence Review Synthesis Contract

Stage 0.14 connects one complete Pareto ranking with enrichment fusion, explicit project
dependency evidence, and multi-snapshot history. It opens only external databases, all in SQLite
read-only/query-only mode, and creates a new sibling synthesis database.

## Lineage and logical validation

Ranking, fusion, dependency, history, and output paths must be distinct siblings. Stage 0.14
recomputes the persisted ranking feature/objective/Pareto/review digests, fusion import/directory
digests, dependency import/graph digests, and history link/file/aggregate digests. Every required
stage and run must be complete.

The ranking and fusion must identify the same structural analysis run. The latest longitudinal
transition referenced by both dependency and history must be identical, and its current analysis
run and inventory session must match the ranking/fusion analysis exactly. Mismatched lineage,
missing candidate-directory evidence, missing project history, table tampering, and output-digest
mismatches fail closed.

## Evidence dimensions

Every ranking candidate retains separate fields for:

- enrichment selection coverage and D2/D3/D4 member counts;
- explicit dependency evaluation state, degrees, centrality, and component-split risk;
- directory history coverage, ambiguity, and churn;
- project activity and historical ambiguity when project context exists.

Coverage is never extrapolated from selected files to unselected files. A candidate outside a
detected project records `NO_PROJECT_CONTEXT`, not zero dependency evidence.

## Review signals

Stage 0.14 emits named, dimension-specific signals such as partial enrichment coverage, confirmed
duplicate members, dependency evidence not evaluated, dependency cut risk, history ambiguity, and
observed churn. Each signal includes only its supporting dimension values.

There is no combined score or priority. Existing objective intervals, Pareto ranks, cohorts, and
review order are not copied or modified. Signals are review aids, not archive eligibility,
importance, deletion safety, or action instructions.

Stage 0.14 contains no source-path access, content hashing, archive, copy, move, rename, delete,
network, shell, subprocess, approval, optimizer, or execution capability.

