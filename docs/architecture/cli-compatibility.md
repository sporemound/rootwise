# CLI Compatibility

The canonical public entry point is `rootwise`. Its six top-level groups match the architectural
domains and dispatch lazily into the existing implementation packages:

```text
rootwise scan
rootwise view
rootwise analyze
rootwise plan
rootwise evidence
rootwise verify
```

The consolidation changes command routing and help names only. Leaf arguments, JSON output,
artifact validation, exit codes, and safety boundaries remain owned by their existing components.

## Canonical operation map

| Canonical operation | Responsibility |
|---|---|
| `rootwise scan ...` | Run the metadata scanner |
| `rootwise scan export ...` | Export one completed inventory session canonically |
| `rootwise scan report ...` | Read an inventory session report |
| `rootwise scan capabilities ...` | Inspect filesystem capabilities for one explicit path |
| `rootwise view search|decide|history|gui ...` | Browse observations and manage separate decisions |
| `rootwise analyze structural ...` | Derive structural roles, aggregates, projects, and relationships |
| `rootwise analyze rank ...` | Derive objectives, Pareto fronts, and a review queue |
| `rootwise analyze fuse ...` | Combine validated structural and enrichment evidence |
| `rootwise analyze temporal ...` | Compare two completed analysis snapshots |
| `rootwise analyze synthesize ...` | Join validated evidence dimensions into review signals |
| `rootwise plan optimize ...` | Produce validated, unapproved proposals |
| `rootwise plan approve ...` | Record selection of one independently validated proposal |
| `rootwise plan preflight ...` | Compile a metadata-only proposal-member manifest |
| `rootwise evidence enrich ...` | Run explicitly permissioned bounded content hashing |
| `rootwise evidence dependency ...` | Import explicit project-dependency evidence |
| `rootwise evidence history ...` | Derive multi-snapshot chain evidence |
| `rootwise verify acceptance ...` | Guide, initialize, record, evaluate, inspect, admit, or verify acceptance/release evidence |

## Compatibility aliases

Earlier console scripts remain installed during the alpha migration. Each writes a deprecation
notice to standard error and then calls the unchanged implementation.

| Compatibility script | Canonical replacement |
|---|---|
| `rootwise-view` | `rootwise view` |
| `rootwise-analyze` | `rootwise analyze structural` |
| `rootwise-rank` | `rootwise analyze rank` |
| `rootwise-optimize` | `rootwise plan optimize` |
| `rootwise-enrich` | `rootwise evidence enrich` |
| `rootwise-approve` | `rootwise plan approve` |
| `rootwise-preflight` | `rootwise plan preflight` |
| `rootwise-fuse-evidence` | `rootwise analyze fuse` |
| `rootwise-longitudinal` | `rootwise analyze temporal` |
| `rootwise-dependency-graph` | `rootwise evidence dependency` |
| `rootwise-history` | `rootwise evidence history` |
| `rootwise-synthesize-evidence` | `rootwise analyze synthesize` |
| `rootwise-acceptance` | `rootwise verify acceptance` |
| `rootwise export|report|capabilities` | `rootwise scan export|report|capabilities` |

No removal release is scheduled. Removing an alias requires a separately reviewed deprecation plan,
documentation and fixture updates, and evidence that supported workflows no longer depend on it.

## Capability preservation

The router imports a domain implementation only after its group and operation are selected. Root
help and unrelated group help therefore do not import the Viewer, Analysis, Planning, Evidence, or
Validation packages. Routing never converts a plan or receipt into execution authority, and the
Evidence content-read acknowledgement remains mandatory at its existing leaf command.

The installed-fixture generators use only the canonical `rootwise` command. Compatibility aliases
are tested as migration surfaces, not used as the project's own primary interface.
