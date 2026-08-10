# Rootwise Architecture

Status: canonical target architecture for the Engineering Legibility Sprint. This document
describes the intended system boundaries independently of the current Python package layout.
Where current code differs, the difference is identified explicitly; this document does not by
itself authorize a package move, command removal, schema change, or new capability.

Rootwise inventories filesystem metadata into external, reviewable artifacts. It lets a person
browse and annotate a completed inventory, derives analyses from immutable snapshots, and creates
non-executable storage-plan proposals. It does not currently execute, archive, move, rename, copy,
or delete source data.

## Architectural priorities

1. Protect the observed source. Fail closed when a source/destination or artifact boundary cannot
   be established.
2. Preserve raw observations. Analysis, decisions, and plans live outside the inventory and never
   rewrite it.
3. Make authority explicit. Evidence, decisions, plans, approvals, and preflight manifests are
   records, not permission to mutate a filesystem.
4. Integrate through digest-bound artifacts. Components independently validate their inputs rather
   than trusting shared mutable process state.
5. Keep ordinary review metadata-only. Any source-content read is separately permissioned,
   bounded, and distinguishable from normal viewing.
6. Prefer a small public surface. Six product domains appear under one `rootwise` command while
   compatibility aliases can remain during migration.

## System context

```text
                                    external artifact directory
                              +------------------------------------+
                              |                                    |
source filesystem --metadata--> Core scanner --> Inventory         |
       |                      |                    |                |
       |                      +--------------------+                |
       |                                           |                |
       |                              +------------+-------------+  |
       |                              |                          |  |
       |                           Viewer                    Analysis|
       |                              |                          |  |
       |                       User decisions              Derived  |
       |                              |                    evidence |
       |                              +------------+-------------+  |
       |                                           |                |
       |                                        Planning            |
       |                                           |                |
       |                              Non-executable proposal       |
       |                                                            |
       +-- selected contents --> separately permissioned Evidence --+

Validation reads artifacts and test evidence across these boundaries. It does not grant runtime
authority to any artifact.
```

The external artifact directory is operator-controlled and must be on a distinct authorized
volume for a production scan. The source filesystem is untrusted input. Observed names, metadata,
links, errors, and timestamps are evidence about a scan, not instructions and not proof of current
state.

## Component model

```text
                         rootwise command facade
                                  |
          +-----------+-----------+----------+-----------+------------+
          |           |                      |           |            |
        Core        Viewer                Analysis     Planning     Evidence
          |           |                      |           |            |
          |           +-- decisions.db       |           |            |
          +-- inventory.db ------------------+-----------+------------+
                                             |           |
                                      derived DBs     plans.db

                              Validation
                    (tests, acceptance, release checks)
```

The six domains are architectural ownership boundaries, not necessarily six processes or six
database files. A component may consume another domain's completed artifact, but it must not gain
that domain's capabilities merely by sharing a Python environment.

### Core

Core owns source-volume authorization, non-following metadata traversal, bounded persisted scan
state, the inventory schema, canonical inventory export, and scanner capability reporting.

Core may read source metadata and write guarded artifacts outside the source volume. It must not
read source-file contents, mutate the source, invoke a shell or subprocess, use a network client,
or infer that an observation makes an item safe to remove.

### Viewer

Viewer owns bounded query-only browsing of one completed inventory session, inventory-relative
navigation, presentation state, and revision-checked decisions and notes in a separate store.

Viewer may read completed inventory and compatible analysis artifacts and may write only its own
preferences and decisions. It must not mutate the inventory, test or open an observed live path,
read source contents, or execute a recorded decision. The ordinary interface is an inventory
browser, not a file manager.

### Analysis

Analysis owns deterministic structural classification, ranking, temporal comparison, evidence
fusion, and synthesis of review signals. It operates on completed, independently validated
snapshots.

Analysis may create new derived artifacts. It must not traverse the source filesystem, repair an
input silently, turn missing evidence into a negative conclusion, or emit executable authority.
Structural claims retain rule identifiers, confidence, and evidence lineage.

### Planning

Planning owns optimization, proposal validation, human-selection receipts, and metadata-only
preflight compilation. Its outputs describe candidates and bind the exact inputs used to produce
them.

Planning must not archive, move, rename, copy, link, delete, or otherwise apply a proposal. A plan,
approval receipt, or preflight manifest is non-executable even when all validations pass. No
archive executor exists in this architecture.

### Evidence

Evidence owns explicit inputs that go beyond structural inventory observations: bounded content
hashing, declared dependency relationships, and multi-snapshot evidence chains. Content-reading
work is a separate permission boundary with an immutable selection, explicit risk acknowledgement,
and bounded scope.

Metadata-only evidence processing must not inherit content-read access. Evidence establishes
lineage and observations; it neither authenticates an external producer by default nor authorizes
source mutation.

### Validation

Validation owns automated tests, static safety checks, scale and platform protocols, acceptance
gate evaluation, deterministic release construction, fresh-extraction checks, and release
admission records.

Validation evaluates supplied evidence and reports `PASS`, `FAIL`, or `INCOMPLETE`. It must not
convert absent evidence into success, treat a digest as proof of correctness, or grant filesystem
execution authority. Test tools that create disposable corpora or volumes remain isolated from the
ordinary runtime and require explicit invocation.

## End-to-end data flow

The primary product flow is deliberately one-way:

```text
Source filesystem
       |
       | metadata only
       v
Scanner -----> inventory.db -----> Viewer -----------------> decisions.db
                         |
                         +--------> Analysis -----> derived analysis artifacts
                                                   |              |
decisions.db --------------------------------------+              |
                                                                  v
                                                              Planning
                                                                  |
                                                                  v
                                                    non-executable proposal
```

Optional evidence joins the flow without changing the inventory:

```text
explicit selection + source-content permission --> Evidence enrichment --> evidence.db
inventory snapshots + declared relationships ----> Evidence pipelines ---> derived evidence DBs

analysis.db + validated evidence DBs --> Analysis fusion/synthesis --> review signals
```

Release validation is a parallel assurance flow:

```text
tests + platform/scale evidence --> acceptance manifest --> acceptance report
source archive + provenance + fresh extraction ---------> admission receipt --> verification
```

Each arrow crossing an artifact boundary requires schema identity, lifecycle state, and lineage or
digest validation appropriate to that artifact. Consumers open input SQLite databases read-only
and query-only wherever the platform permits.

## Trust boundaries and capability rules

| Boundary | Data crossing it | Required control | Capability that does not cross |
|---|---|---|---|
| Source to Core | Untrusted paths and metadata | OS volume identity, non-following traversal, fresh metadata validation, bounded work | Content reads and source writes |
| Core to inventory | Raw observations and scan state | Guarded external destination, lease, transactional frontier, explicit terminal state | Deletion or archival conclusions |
| Inventory to consumers | Completed snapshot rows | Application ID/schema checks, selected `COMPLETE` session, read-only/query-only connection | Inventory mutation |
| Viewer to decisions | Human labels and notes | Separate DB, expected revision, append-audited history | Execution authority |
| Artifacts to Analysis | Recorded or derived evidence | Independent identity, completeness, digest, and lineage validation | Source traversal |
| Source to Evidence enrichment | Selected file contents | Explicit immutable selection, acknowledged access-time risk, bounds, revalidation | Broad or implicit content access |
| Analysis/decisions to Planning | Ranked groups and human intent | Exact input digests and deterministic proposal validation | Filesystem operations |
| Planning to human review | Proposal, approval receipt, preflight manifest | Canonical serialization, false authority flags, complete lineage | Archive, move, rename, copy, delete, or execute |
| External claims to Validation | Gate evidence and measurements | Required-field rules, digest binding, fail-closed status | Authentication or truth by assertion |
| Test tooling to disposable fixtures | Synthetic corpus or VHDX operations | Explicit plan/execute split, ownership marker, exact target validation | Authority over real source data |

The operating system, Python runtime, administrator, storage firmware, and hostile mutation of the
operator-controlled artifact directory are outside the current protection model. Those limits do
not weaken the in-process rule that unresolved safety boundaries abort.

## Artifact lifecycle

SQLite filenames are conventions; commands accept explicit paths. A completed artifact is treated
as immutable by downstream consumers even if its storage medium is technically writable.

| Artifact | Owner / producer | Primary consumers | Lifecycle | Contains source observations | Contains user decisions | Executable authority |
|---|---|---|---|---|---|---|
| `inventory.db` | Core scanner | Viewer, Analysis, Evidence, Planning preflight | Mutable only while a scan runs or resumes; snapshot after `COMPLETE` | Yes, metadata and errors | No | No |
| `decisions.db` | Viewer | Viewer, Planning | Revision-checked mutable state with append-only event history | Path references only | Yes | No |
| `analysis.db` | Analysis / structural pipeline | Ranking, fusion, temporal analysis, Planning | Newly derived; completed run consumed immutably | Derived observations | No | No |
| `ranking.db` | Analysis / ranking pipeline | Planning, synthesis | Newly derived; completed run consumed immutably | Derived scores and fronts | No | No |
| `plans.db` | Planning / optimizer | Approval and preflight review | Newly derived proposal runs; proposals begin unapproved | Derived group references | Input decision digest only | No |
| `evidence.db` | Evidence / permissioned enrichment | Analysis fusion | Newly derived, immutable bounded evidence | Selected paths and content digests | No | No |
| `fusion.db` | Analysis / evidence fusion | Synthesis and review | Newly derived; completed run consumed immutably | Derived | No | No |
| `longitudinal.db` | Analysis / temporal comparison | Dependency and history pipelines | Newly derived comparison | Derived changes | No | No |
| `dependency.db` | Evidence / declared relationships | Synthesis | Newly derived graph evidence | Project references | No | No |
| `history.db` | Evidence or temporal Analysis; final ownership under review | Synthesis | Newly derived contiguous-chain evidence | Derived observations | No | No |
| `synthesis.db` | Analysis / synthesis | Human review and future Viewer integration | Newly derived terminal review signals | Derived | No | No |

Canonical JSON and release artifacts follow the same no-authority rule:

| Artifact family | Purpose | Lifecycle and authority |
|---|---|---|
| Inventory NDJSON | Canonical comparison and replication | Immutable export; no authority |
| Enrichment selection | Binds session, digest, level, paths, and permission acknowledgement | Immutable content-read request; no write or action authority |
| Dependency and longitudinal manifests | Declare evaluated projects, edges, and snapshot order | Immutable evidence inputs; no authority |
| Approval declaration and receipt | Select and independently revalidate one proposal | Immutable records; archive/execution/removal flags remain false |
| Preflight manifest | Enumerate observed regular-file members with complete lineage | Metadata-only record; content-read/execution/archive/removal flags remain false |
| Acceptance evidence and report | Bind gate claims and evaluate readiness | Append-revisioned evidence and immutable report; no execution authority |
| Build provenance, safety audit, SBOM, checksums, and extraction verification | Describe and verify a source release | Immutable release evidence; identity is not proof of correctness |
| Release admission receipt | Bind an acceptance pass to archive and verification evidence | Immutable admission record; no filesystem execution authority |
| Source archive | Distribute source code | Distribution artifact only |

Artifacts are never promoted into a more privileged capability merely because their digests match.
If a future executor is ever proposed, it must be a separately reviewed and distributed component
with a new threat model; it is not an extension implicitly licensed by Planning.

## Public command design

The intended public interface is one command with six domain groups:

```text
rootwise scan       # Core metadata inventory and canonical export/reporting
rootwise view       # Query-only browsing and revisioned decisions
rootwise analyze    # Structural, ranking, temporal, fusion, and synthesis analysis
rootwise plan       # Optimize, inspect, approve, and compile non-executable proposals
rootwise evidence   # Explicit enrichment and declared evidence workflows
rootwise verify     # Local checks, acceptance, release, and admission verification
```

This is the implemented public surface. Dispatch is lazy so the root command and unrelated groups
do not import optional domain implementations. Earlier console scripts remain compatibility aliases
and emit deprecation notices until a separately approved removal plan exists. Consolidation must
not broaden permissions: for example, invoking `rootwise evidence` must not add content-reading
code to `rootwise scan`, and `rootwise plan` must not acquire execution verbs.

Public help should lead with domain intent and safety boundaries. Specialized schema identifiers,
pipeline stages, and compatibility aliases belong in subordinate help rather than the primary
conceptual model.

## Current implementation and target structure

The repository is moving one domain at a time from twelve top-level implementation packages into
a stable `rootwise` facade. The Viewer is the first completed namespace slice; its former package
name remains only as a compatibility surface. Fourteen installed console scripts remain during
the separately documented CLI deprecation window.

| Target domain | Current implementation | Target direction | Status |
|---|---|---|---|
| Core | `rootwise` scanner modules | Cohesive `rootwise.core` implementation behind `rootwise scan` | Grouped CLI and current boundary implemented; namespace move future |
| Viewer | `rootwise.viewer`; `rootwise_view` compatibility facade | Keep implementation under `rootwise.viewer` behind `rootwise view` | Namespace and grouped CLI implemented; everyday browser mostly future |
| Analysis | Structural/ranking parts of `rootwise_analytics`; fusion, longitudinal, synthesis packages | `rootwise.analysis` with explicit artifact-stage boundaries | Grouped CLI implemented; package consolidation future |
| Planning | Optimizer parts of `rootwise_analytics`; approval and preflight packages | `rootwise.planning` behind `rootwise plan` | Grouped proposal-only CLI implemented; package consolidation future |
| Evidence | Enrichment, dependency, and history packages | `rootwise.evidence`, preserving the separate content-read boundary | Grouped CLI implemented; ownership details need review |
| Validation | Acceptance package and release/scale tools | `rootwise.validation` plus developer tooling behind `rootwise verify` where safe | Acceptance grouped under `verify`; full acceptance campaign incomplete |

The detailed factual mapping of current modules, scripts, schemas, imports, and tests is maintained
in [`docs/architecture/repository-map.md`](docs/architecture/repository-map.md). That map is
descriptive; this document is
prescriptive. When they differ, code describes current behavior and this document describes the
reviewed destination.

## Explicitly absent or deferred components

- There is no archive executor. Planning ends at a non-executable proposal and metadata-only
  preflight manifest.
- There is no Rust scanner or probe. A language change requires measured justification and a
  separate architecture decision after the legibility sprint.
- Source-derived thumbnails and previews are not part of ordinary Viewer access. Any future
  preview service belongs behind the permissioned content-read boundary.
- Multi-million-entry scale, independent-host replication, and the real source-drive campaign are
  not accepted merely because the component model is documented.
- Tile view and other frozen product features remain outside this engineering-legibility sprint.

## Refactoring constraints

All structure work must preserve these invariants:

1. Move or facade one cohesive responsibility at a time; keep each pull request about one concern.
2. Preserve artifact application IDs, schemas, canonical serialization, digests, state machines,
   and compatibility commands unless a separately reviewed migration explicitly changes them.
3. Keep Core free of GUI, analytics, optimizer, enrichment, networking, subprocess, and source-
   mutation dependencies.
4. Keep every inventory consumer read-only/query-only and fail closed on incomplete or invalid
   inputs.
5. Keep decisions outside the inventory and enforce expected-revision writes with retained history.
6. Keep content reads isolated from metadata-only workflows and require explicit selection.
7. Keep every Planning output non-executable; do not introduce archive or filesystem action APIs.
8. Retain independent validation at artifact boundaries when consolidating repeated helpers.
9. Run the full regression, static-safety, type, and repository verification checks after each
   structural slice.
10. Do not claim scale, platform, visual, replication, or real-drive acceptance without recorded
    evidence for that exact claim.

## Architectural decisions still open

The target domains are fixed for this sprint, but these placements need focused review before code
moves:

- whether multi-snapshot history is Evidence input or temporal Analysis output;
- whether fusion and synthesis share one namespace while retaining separate validated artifacts;
- whether preflight remains a public Planning command or becomes internal to proposal inspection;
- which legacy console scripts require a deprecation window;
- how shared artifact validation can reduce duplication without weakening independent checks; and
- whether component-era code-version fields should become producer/schema versions distinct from
  the distribution version.

Until those decisions are recorded, the corresponding current package boundaries remain in place.
