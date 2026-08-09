# 0.4 Structural Analytics Trust Model

`paretodrive-analyze` consumes one `COMPLETE` inventory session through SQLite URI `mode=ro` and
`PRAGMA query_only=ON`. It never receives, resolves, stats, or opens an observed source path.

Analysis output is a distinct SQLite file in the inventory database's already-approved external
directory. Raw observations remain immutable. Each stage records its input, configuration, output,
code version, state, and error. A failed run cannot appear complete.

0.4 uses metadata-only deterministic rules. Roles and project boundaries carry rule IDs,
confidence, and evidence; they are not deletion advice. Missing evidence produces `UNKNOWN`, not a
negative value judgment. Relationship evidence is structural only and does not claim that file
contents or dependency manifests were inspected.

The implementation is functionally tested on deterministic fixtures. It is not yet benchmarked or
resource-qualified at multi-terabyte inventory cardinality.
