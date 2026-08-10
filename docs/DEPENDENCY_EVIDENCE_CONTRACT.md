# 0.12 Explicit Project-Dependency Evidence Contract

Stage 0.12 adds stronger project relationships without granting ParetoDrive permission to inspect
source content. It consumes one canonical JSON evidence manifest bound to one complete Stage 0.11
run and writes a new sibling SQLite database. The longitudinal database is opened read-only and
query-only; the evidence manifest is read as data; no recorded source path is opened.

## Evidence boundary

The manifest must use schema `paretodrive-project-dependency-evidence-v1`, identify the exact
longitudinal run and output digest, name its producer and creation time, list every project the
producer actually evaluated, and provide a sorted set of evidence records. Supported relationship
types are:

- `DEPENDS_ON`
- `REFERENCES`
- `GENERATED_FROM`
- `EXPORTS_TO`
- `SHARES_ASSETS_WITH`

Each evidence record has an identifier, two known active projects, confidence in `[0,1]`, and a
bounded human-readable evidence reference. Stage 0.12 does not authenticate the producer or open
the referenced material. A manifest therefore records supplied evidence, not independently proven
source semantics.

Projects omitted from `evaluated_projects` are `NOT_EVALUATED`; zero imported edges must never be
interpreted as proof of independence. Coverage is evaluated active projects divided by all active
projects. Removed and unknown projects, self-edges, duplicate edges, unsupported relationship
types, non-canonical JSON or undirected endpoint ordering, malformed keys, and digest mismatches
fail closed.

## Graph semantics

Only explicit `DEPENDS_ON` records contribute to dependency in/out degree, weighted dependency
degree, and PageRank-style centrality. All supported relationships contribute to weak components,
relationship degree, and the transparent component-split count called dependency cut risk.
These are navigation and review features, not value or disposal scores.

The output records `validate`, `import_evidence`, and `graph_features` stages with input,
configuration, output, and code digests. Stage 0.12 contains no content hashing, source-content
reads, archive, copy, move, rename, delete, network, shell, subprocess, approval, or execution
capability.
