# Rootwise Repository Map

Status: Milestone L1 inventory only. Baseline commit:
`6345dc7bbe3060d18ea4b54b45f1bab41b1dbbd3` (`0.23.0-alpha`).

Post-baseline status: the L5 Viewer slice moved implementation to `rootwise.viewer`; the mapped
`rootwise_view` name now remains as a compatibility facade. The inventory below is intentionally
preserved as the factual pre-refactor baseline for the remaining namespace moves.

This document describes the repository as it exists before namespace, CLI, or documentation
consolidation. It is factual unless a row is explicitly labeled **proposed**. No production code
was changed to produce this map.

## The five-minute model

1. **What does Rootwise do?** It inventories filesystem metadata into an external SQLite database,
   presents bounded read-only review, derives snapshot analytics, and produces non-executable
   storage-plan proposals.
2. **What are the major conceptual domains?** Core, Viewer, Analysis, Planning, Evidence, and
   Validation. The current Python layout exposes twelve packages rather than those six domains.
3. **What can touch the source filesystem?** The core scanner reads metadata. The separately
   permissioned enrichment process can read selected file contents. Production viewer, analysis,
   planning, and validation components do not open observed source paths. Test tools can create a
   disposable corpus or manage a disposable VHDX only with explicit execution.
4. **How does data move?** Components usually exchange immutable, digest-bound SQLite or canonical
   JSON artifacts. Cross-package Python imports exist, but artifact lineage—not in-memory calls—is
   the main integration boundary.
5. **What is mature?** The scanner boundary and synthetic regression suite are implemented and
   locally tested. The ordinary browser experience is mostly designed, not implemented. Large
   scale, independent replication, and the real source-drive campaign are incomplete. No archive
   executor exists.

## Repository snapshot

| Inventory item | Current count | Legibility observation |
|---|---:|---|
| Importable top-level Python packages | 12 | Six conceptual domains are exposed as twelve names. |
| Production Python modules | 67 | Package sizes range from 3 to 15 modules. |
| Installed console scripts | 14 | Only `rootwise` is a grouped root command today. |
| SQLite application identities | 11 | Each persisted stage has a distinct database identity. |
| Test modules | 57 | 131 tests passed on the mapped baseline. |
| Flat files directly under `docs/` | 38 | No hierarchy or index currently separates active, protocol, and historical material. |
| Root files | 11 | `ARCHITECTURE.md`, `DEVELOPMENT.md`, and `SECURITY.md` do not yet exist. |
| Runtime dependencies | 0 core | Viewer, analytics, optimizer, and enrichment dependencies are optional and separately locked. |

`src/rootwise.egg-info/` exists in the working environment as generated editable-install metadata;
it is ignored and not tracked source.

## Current source packages

The **Proposed L5 action** is a mapping aid, not an approved refactor. **Review decision** remains
`UNSURE` until the map is reviewed using `KEEP`, `RENAME`, `MOVE`, `MERGE`, `ARCHIVE`, or `UNSURE`.

| Current package | Modules | Current responsibility | Direct internal imports / artifact dependencies | Source access | Proposed domain and L5 action | Review decision |
|---|---:|---|---|---|---|---|
| `rootwise` | 12 | Scanner, volume identity, write guard, resources, inventory DB, canonical export, reports, capabilities, root CLI | Self-contained core; produces inventory and NDJSON | Metadata traversal; no content reads | Keep `rootwise` facade; **MOVE** implementation under `rootwise.core` | `UNSURE` |
| `rootwise_view` | 5 | Query-only inventory reader, decision DB, CLI, PySide6 GUI | Imports product version from `rootwise`; reads inventory; writes decisions | Does not open observed source paths | **MOVE** to `rootwise.viewer` | `UNSURE` |
| `rootwise_analytics` | 15 | Structural analysis, ranking, exact/MOEA optimization, plan validation | Reads inventory, analysis, ranking, and decisions artifacts | Snapshot-only | **MOVE** structural/ranking to `rootwise.analysis`; optimizer/plan modules to `rootwise.planning` | `UNSURE` |
| `rootwise_enrich` | 5 | Explicit selection validation and bounded D2/D3/D4 content hashing | Imports core volume/models/errors; reads inventory and selection; writes enrichment evidence DB | Explicit, acknowledged content reads | **MOVE** to `rootwise.evidence.enrichment` | `UNSURE` |
| `rootwise_fusion` | 3 | Validates and combines structural analysis with enrichment evidence | Imports analysis identity; reopens analysis and enrichment DBs | None | **MERGE** into `rootwise.analysis.evidence_fusion` | `UNSURE` |
| `rootwise_longitudinal` | 3 | Compares two snapshots and derives temporal/project relationships | Imports analysis and inventory identities; reads two analysis/inventory chains | None | **MERGE** into `rootwise.analysis.temporal` | `UNSURE` |
| `rootwise_dependency` | 3 | Imports explicit project-dependency evidence and derives graph features | Imports longitudinal identity; reads longitudinal DB and evidence manifest | None | **MOVE** to `rootwise.evidence.dependency` | `UNSURE` |
| `rootwise_history` | 3 | Validates contiguous longitudinal chains and derives multi-snapshot features | Imports longitudinal identity; reads chain manifest and longitudinal DBs | None | **MOVE** to `rootwise.evidence.history` or `rootwise.analysis.temporal`; exact home needs review | `UNSURE` |
| `rootwise_synthesis` | 3 | Joins ranking, fusion, dependency, and history evidence for review signals | Imports five package identities/helpers; reads five derived DB lineages | None | **MERGE** into `rootwise.analysis.evidence_fusion` or `review` | `UNSURE` |
| `rootwise_approval` | 4 | Validates one proposal and emits a non-executable approval receipt | Imports optimizer models, identity, and validator; reads plans DB | None | **MERGE** into `rootwise.planning.approval` | `UNSURE` |
| `rootwise_preflight` | 4 | Traces approved plan lineage and emits metadata-only member manifest | Imports approval plus inventory/analysis/ranking/plan identities | None | **MERGE** into `rootwise.planning.preflight` | `UNSURE` |
| `rootwise_acceptance` | 7 | Acceptance manifest workflow, gate recording/evaluation, release admission and verification | Standalone canonical JSON logic; consumes external evidence and release artifacts | None | **MOVE** to `rootwise.validation` | `UNSURE` |

## Current installed command surface

Compatibility aliases can remain during consolidation. The final column is proposed by the sprint
brief and is not implemented.

| Installed command | Current operation | Primary input/output | Proposed grouped command | Review decision |
|---|---|---|---|---|
| `rootwise` | `scan`, `export`, `report`, `capabilities` | Source metadata → inventory/NDJSON/report | Retain; expand as the public command root | `UNSURE` |
| `rootwise-view` | `search`, `decide`, `history`, `gui` | Inventory + decisions | `rootwise view ...` | `UNSURE` |
| `rootwise-analyze` | Structural roles, aggregates, projects, relationships | Inventory → analysis DB | `rootwise analyze structural ...` | `UNSURE` |
| `rootwise-rank` | Objectives, Pareto fronts, review queue | Analysis → ranking DB | `rootwise analyze rank ...` | `UNSURE` |
| `rootwise-optimize` | Exact/evolutionary proposal generation | Ranking + decisions → plans DB | `rootwise plan optimize ...` | `UNSURE` |
| `rootwise-enrich` | Explicit content hashing | Inventory + selection + source → evidence DB | `rootwise evidence enrich ...` | `UNSURE` |
| `rootwise-approve` | Non-executable proposal approval receipt | Plans + declaration → receipt JSON | `rootwise plan approve ...` | `UNSURE` |
| `rootwise-preflight` | Metadata-only member compilation | Plans + receipt + inventory → manifest JSON | `rootwise plan preflight ...` | `UNSURE` |
| `rootwise-fuse-evidence` | Structural/enrichment fusion | Analysis + evidence → fusion DB | `rootwise analyze fuse ...` | `UNSURE` |
| `rootwise-longitudinal` | Two-snapshot comparison | Two analysis DBs → longitudinal DB | `rootwise analyze temporal ...` | `UNSURE` |
| `rootwise-dependency-graph` | Explicit dependency evidence | Longitudinal + manifest → dependency DB | `rootwise evidence dependency ...` | `UNSURE` |
| `rootwise-history` | Multi-snapshot temporal aggregation | Chain manifest → history DB | `rootwise evidence history ...` | `UNSURE` |
| `rootwise-synthesize-evidence` | Multi-evidence review synthesis | Ranking + fusion + dependency + history → synthesis DB | `rootwise analyze synthesize ...` | `UNSURE` |
| `rootwise-acceptance` | `init`, `guide`, `record`, `evaluate`, `inspect`, `admit`, `verify-admission` | Evidence/release JSON chain | `rootwise verify acceptance ...` and `rootwise verify admission ...` | `UNSURE` |

## Non-installed developer and acceptance tools

| Tool group | Files | Responsibility | Proposed home/action | Review decision |
|---|---|---|---|---|
| Environment | `tools/bootstrap.py` | Creates a locked development environment | Developer workflow; **KEEP** | `UNSURE` |
| Local verification | `tools/verify.py`, `verify_release.py`, `build_release.py` | Tests, evidence capture, deterministic archive, fresh extraction | Validation tooling; **KEEP**, later expose through `rootwise verify` only where safe | `UNSURE` |
| Platform protocol | `tools/windows_exfat_vhdx.ps1` | Plan/execute harness for disposable Windows exFAT VHDX | Protocol tooling; **KEEP** isolated from runtime | `UNSURE` |
| Scale preparation | `tools/prepare_scale_corpus.py` | Explicit disposable zero-byte corpus and query generation | Validation/scale; **MOVE** conceptually | `UNSURE` |
| Scale measurement | `tools/run_scale_acceptance.py` | Scanner, viewer, and snapshot resource measurement | Validation/scale; **MOVE** conceptually | `UNSURE` |
| Installed-fixture generators | Seven `generate_*_evidence.py` scripts | Exercise installed CLI chains on temporary synthetic artifacts | Test/validation helpers; **MERGE** behind one fixture driver later | `UNSURE` |

## Python import graph

The direct cross-package imports are intentionally sparse:

```text
rootwise_view ───────────────→ rootwise (version only)
rootwise_enrich ─────────────→ rootwise (errors, models, volume)

rootwise_fusion ─────────────→ rootwise_analytics
rootwise_longitudinal ───────→ rootwise_analytics
rootwise_dependency ─────────→ rootwise_longitudinal
rootwise_history ────────────→ rootwise_longitudinal
rootwise_synthesis ──────────→ rootwise_analytics
             ├───────────────→ rootwise_fusion
             ├───────────────→ rootwise_dependency
             └───────────────→ rootwise_history

rootwise_approval ───────────→ rootwise_analytics
rootwise_preflight ──────────→ rootwise_approval
             └───────────────→ rootwise_analytics

rootwise_acceptance           (no production-package imports)
```

Most arrows import application IDs, schema constants, validators, or data models. The heavier
runtime coupling occurs through files, shown next.

## Persisted-artifact data flow

```text
Source filesystem metadata
        ↓ rootwise scan
inventory.db ───────────────→ rootwise-view
        ├───────────────────→ structural analysis → analysis.db
        │                                              ↓
        │                                      ranking.db
        │                                              ↓ + decisions.db
        │                                         plans.db
        │                                      ↙               ↘
        │                            approval receipt      preflight manifest
        │
        └─ + selection + explicit source-content permission
                           ↓
                      evidence.db
                           ↓ + analysis.db
                       fusion.db

analysis.db (baseline + current) → longitudinal.db
                                      ├─ + dependency manifest → dependency.db
                                      └─ chain manifest ───────→ history.db

ranking.db + fusion.db + dependency.db + history.db → synthesis.db

external gate evidence + measurements → acceptance manifest → acceptance report
acceptance report + archive + build provenance + extraction verification
                                                  → admission receipt → verification
```

Every plan and approval shown above remains non-executable.

## SQLite artifact inventory

Names are conventions; CLIs generally accept arbitrary explicit paths. “Immutable” means the
producer creates a new artifact or completed run that downstream readers treat as immutable.

| Conventional artifact | App ID | Producer | Consumers | Lifecycle | Source observations | User decisions | Executable authority |
|---|---:|---|---|---|---|---|---|
| `inventory.db` | 1346654806 | Core scanner | Viewer, analysis, enrichment, preflight, scale tools | Mutable while scanning/resuming; snapshot after `COMPLETE` | Yes | No | No |
| `decisions.db` | 1346654807 | Viewer decision store | Viewer, optimizer | Mutable, revision-checked, append-audited | References paths | Yes | No |
| `analysis.db` | 1346654808 | Structural analysis | Ranking, fusion, temporal, preflight, synthesis | New derived DB; completed run consumed immutably | Derived from observations | No | No |
| `ranking.db` | 1346654809 | Ranking pipeline | Optimizer, synthesis, preflight | New derived DB | Derived | No | No |
| `plans.db` | 1346654810 | Optimizer | Approval, preflight | New proposal DB; all plans `UNAPPROVED` | References derived groups | Decision digest only | No |
| `evidence.db` | 1346654811 | Permissioned enrichment | Fusion | New evidence DB | Selected paths + content digests | No | No |
| `fusion.db` | 1346654812 | Evidence fusion | Synthesis | New derived DB | Derived | No | No |
| `longitudinal.db` | 1346654813 | Temporal comparison | Dependency, history | New derived DB | Derived changes | No | No |
| `dependency.db` | 1346654814 | Dependency evidence analysis | Synthesis | New derived DB | Project references | No | No |
| `history.db` | 1346654815 | Multi-snapshot history | Synthesis | New derived DB | Derived observations | No | No |
| `synthesis.db` | 1346654816 | Review synthesis | Human review / later viewer integration | New terminal review DB | Derived | No | No |

## Canonical JSON, text, and release artifacts

| Artifact or schema | Producer | Purpose / consumer | Authority |
|---|---|---|---|
| Canonical inventory NDJSON (schema 2) | Core canonical export | Cross-platform inventory comparison and replication | None |
| `rootwise-enrichment-selection-1` | Operator | Pins session, digest, level, and selected content-read paths | Content-read request only; no action authority |
| `rootwise-project-dependency-evidence-v1` | External/operator | Declares evaluated projects and explicit dependency edges | Evidence only |
| `rootwise-longitudinal-chain-v1` | Operator/tooling | Orders contiguous longitudinal artifacts for history | None |
| `rootwise-plan-approval-declaration-1` | Operator | Selects one proposal and binds digests | Selection intent only |
| `rootwise-plan-approval-receipt-1` | Approval component | Records independently revalidated plan selection | Archive/execution/removal flags are false |
| `rootwise-executor-preflight-manifest-1` | Preflight compiler | Enumerates observed regular-file members and lineage | Content-read/execution/archive/removal flags are false |
| `rootwise-acceptance-evidence-v1` | Acceptance workflow + external evidence | Immutable revisions containing nine gate claims/digests | Readiness evidence only |
| Gate evidence and measurements JSON | External procedures / scale tool | Raw review material referenced by acceptance manifest | None |
| `rootwise-acceptance-report-v1` | Acceptance evaluator | Canonical `PASS`/`FAIL`/`INCOMPLETE` evaluation | None |
| `rootwise-release-admission-v1` | Admission component | Binds a complete pass to archive/provenance/verification | No filesystem execution authority |
| Scale corpus ownership marker / manifest / query JSON | Scale preparation tool | Resumable disposable fixture identity and viewer queries | Test-fixture ownership only |
| `rootwise-scale-evidence-v1` + measurements | Scale runner | Scanner/viewer/snapshot resource observations | Evidence only |
| `SOURCE_MANIFEST.json`, platform test JSON, `SAFETY-AUDIT.json`, `SBOM.json`, `BUILD_PROVENANCE.json` | `tools/verify.py` | Local build and test evidence | None |
| `VERIFY-RELEASE.json` | `tools/verify_release.py` | Fresh-extraction verification result | None |
| `SHA256SUMS.txt` | Verification tooling | Artifact identity list | Identity, not correctness |
| `rootwise-0.23.0-alpha-source.zip` | Release builder | Deterministic source archive | Source distribution only |

## Trust-boundary map

| Domain today | May read source metadata | May read source contents | May write | Explicitly cannot do |
|---|---|---|---|---|
| Core scanner (`rootwise`) | Yes | No | Guarded external inventory/export/error outputs | Source mutation, archive, network, subprocess |
| Viewer (`rootwise_view`) | No; reads recorded observations | No | Separate decisions DB | Inventory mutation and live-path actions |
| Analysis and temporal/evidence joins | No | No | New external derived DBs | Source traversal and execution |
| Planning, approval, preflight | No | No | New proposal DB / canonical receipts/manifests | Archive creation, move, rename, delete, execution |
| Enrichment (`rootwise_enrich`) | Revalidates selected metadata | Yes, only explicit bounded selection | New evidence DB | Source writes and action authorization |
| Acceptance/admission | No | No | New canonical JSON evidence/report/receipt files | Evidence authentication and filesystem execution |
| VHDX acceptance tool | Disposable test image/volume only | Fixture-specific | Explicit test artifacts and optional disposable volume operations | Ordinary runtime use; real source drive |
| Scale corpus tool | No user-source access | No | Explicit new disposable zero-byte fixture tree | Overwrite, automatic cleanup, real-drive targeting |

There is no archive executor package, binary, or public command.

## Repeated concepts and structural friction

These are consolidation candidates, not permission to change behavior:

1. **Pipeline scaffolding is repeated.** Analysis, ranking, optimizer, enrichment, fusion,
   longitudinal, dependency, history, and synthesis independently define run/stage tables,
   timestamps, canonical JSON, row digests, application-ID checks, state transitions, and result
   dataclasses.
2. **Artifact readers repeat fail-closed SQLite validation.** Multiple packages independently open
   query-only databases, check application IDs, select a complete run, validate stage digests, and
   close connections. Consolidation could remove duplication, but must preserve independent
   validation rather than introducing trusted shared mutable state.
3. **Canonical JSON helpers are duplicated.** `_canonical`, `_digest`, bounded-string/number
   validation, exclusive output creation, and file hashing recur across evidence, planning,
   acceptance, and tools.
4. **Application IDs are duplicated across packages.** Inventory identity appears in core, viewer,
   and analytics; enrichment identity appears in enrichment and fusion. A read-only artifact-type
   registry may improve legibility if it does not create unwanted imports into the scanner.
5. **CLI wrappers are nearly identical.** Most three-module packages contain `__init__.py`,
   `cli.py`, and one `pipeline.py`. Fourteen installed scripts expose implementation chronology
   rather than user tasks.
6. **`rootwise_analytics` contains two domains.** Structural/ranking analysis and proposal-only
   planning/optimization currently share one top-level package.
7. **Evidence terminology overlaps.** Enrichment evidence, dependency evidence, fusion, synthesis,
   acceptance evidence, build evidence, and scale evidence are distinct but presented as peers.
8. **Component versions encode chronology.** Pipeline constants and docstrings still say 0.4,
   0.7, 0.10, and similar stage numbers while the distribution is 0.23.0-alpha.
9. **Artifact names require historical knowledge.** `fusion`, `synthesis`, `longitudinal`,
   `admission`, and `preflight` describe implementation stages more than the six intended domains.
10. **Documentation is flat and chronology-heavy.** Thirty-eight top-level docs mix active trust
    models, feature contracts, platform protocols, acceptance procedures, and historical migration
    records without an index.

## Consolidation opportunities by intended domain

| Intended domain | Current packages/modules | Smallest plausible first move | Safety constraint |
|---|---|---|---|
| Core | `rootwise` scanner modules | Introduce `rootwise.core` facades or move one cohesive group | Scanner dependency surface must not grow |
| Viewer | `rootwise_view` | Move with compatibility imports and console alias | Inventory remains URI read-only/query-only |
| Analysis | Structural/ranking parts of `rootwise_analytics`, plus fusion/longitudinal/synthesis | Move one pipeline per PR | Preserve artifact and digest validation |
| Planning | Optimizer parts of `rootwise_analytics`, approval, preflight | Move data models/validator before orchestration | No executable semantics or silent plan repair |
| Evidence | Enrichment, dependency, history | Consolidate names first; keep permissioned content boundary explicit | Metadata-only evidence must not inherit content-read capability |
| Validation | Acceptance/admission plus scale/release tools | Group public command and docs before internals | External claims remain unauthenticated and fail closed |

## Documentation and test topology

The primary landing page is `README.md`. Detailed documents are all flat under `docs/`; there is no
documentation index. The intended three-document developer path—`README.md`, `ARCHITECTURE.md`,
`DEVELOPMENT.md`—is not yet available. `SECURITY_REVIEW.md` and `THREAT_MODEL.md` exist under
`docs/`, but the root has no `SECURITY.md` entry point.

Tests are also flat, but their names align well with implementation responsibilities. Most
source-facing or artifact-consuming packages have both behavioral and static-safety tests. The
test suite is therefore a useful safety net for later one-package-at-a-time moves even though the
production namespace is fragmented.

## Current maturity by conceptual domain

| Domain | Implemented | Key limitations / not tested |
|---|---|---|
| Core | Metadata scanner, volume boundary, guarded SQLite, cancellation/resume, canonical export | Real 3.9+ TB drive prohibited; independent replication absent |
| Viewer | Query-only search, bounded pages, decisions/history, basic GUI/menu | Approved details/compact/navigation architecture not implemented; no scale UI campaign |
| Analysis | Structural roles, ranking, temporal/dependency/history/fusion/synthesis pipelines | Mostly synthetic small fixtures; multi-million behavior not accepted |
| Planning | Exact/MOEA proposals, deterministic validation, approval and preflight | Proposal-only; large-tree convergence and resource behavior not accepted |
| Evidence | Explicit bounded enrichment plus dependency/history declarations | Content enrichment only small synthetic selections; producer authentication absent |
| Validation | Acceptance evaluation/recording, admission, chain verification, scale harness | Real report remains incomplete; independent reproduction and million-entry run absent |
| Executor | Nothing | Deliberately future, separately distributed component |
| Rust | Nothing | Architecture decision and measured probe are future work, frozen during this sprint |

## L1 review worksheet

Reviewers should update the **Review decision** cells in the package, command, and tool tables using
only:

```text
KEEP     responsibility and name are already clear
RENAME   responsibility is correct but the name obscures it
MOVE     responsibility belongs under another domain
MERGE    standalone boundary adds more complexity than isolation value
ARCHIVE  historical or superseded material should leave the primary path
UNSURE   more evidence or discussion is required
```

Questions to resolve before L2/L4/L5:

1. Should history be evidence input or temporal analysis output?
2. Should fusion and synthesis become one analysis namespace while remaining separate artifact
   validation steps?
3. Should preflight remain public under Planning, or be internal preparation behind `plan inspect`?
4. Which compatibility console scripts need a deprecation window?
5. Can shared artifact-validation helpers remain independent enough to preserve defense in depth?
6. Should component-era `CODE_VERSION` fields become schema/producer versions distinct from the
   distribution release version?

No answer in this L1 map authorizes a package move, CLI change, schema change, or safety-boundary
change.
