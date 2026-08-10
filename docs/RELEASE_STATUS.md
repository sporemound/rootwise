# Release Status

Version: `0.23.0-alpha` (unreleased source milestone)

- Designed: metadata-only scanner boundary and staged release gates.
- Implemented: volume identity, guarded outputs, handle-bound traversal, SQLite sessions,
  cancellation/resume, structured errors, and deterministic canonical export.
- Viewer implemented: query-only inventory reader, bounded search, separate revisioned decisions,
  persistent decision/revision/note columns, palette-safe recorded state, synchronized editing,
  functional File/View/Decisions/Help menus, headless CLI, and optional PySide6 table interface.
- Product experience contract designed: shared bounded result pages, details/compact/tile modes,
  inventory-only navigation, presentation preferences, keyboard/context-menu behavior, ordinary
  states, metadata inspector and permissioned-preview boundaries, accessibility, and high-DPI
  requirements are classified by capability. Stage 0.24 changes no runtime behavior; the proposed
  default modes, columns, tile size, session scope, and Explorer conventions await user approval.
- Structural analytics implemented: snapshot-only deterministic roles, recursive directory totals,
  project-marker boundaries, structural relationships, and per-stage provenance.
- Pareto review implemented: DuckDB/Polars feature materialization, independent confidence
  intervals, cohort-local robust fronts, and a bounded human-review queue in a third database.
- Proposal optimizer implemented: explicit hierarchical candidates, exact tree Pareto reference,
  fixed-seed NSGA-III, R-NSGA-III refinement with explicit degeneracy fallback, independent plan
  validation, hard capacity constraints, and `UNAPPROVED` reduced presentation.
- Permissioned enrichment implemented: immutable explicit selections, D2 sampled BLAKE3, D3 full
  BLAKE3, D4 full SHA-256, bounded/rate-limited reads, path and metadata revalidation, and a
  separate evidence database. D2 groups remain `CANDIDATE`; D3/D4 groups are byte-equality
  evidence only and authorize no action.
- Non-executing plan approval implemented: strict digest-bound declarations, query-only plan
  consumption, independent selected-plan revalidation, bounded canonical receipt export, and
  explicit false execution/archive/removal authorization fields.
- Metadata-only executor preflight implemented: full plans/ranking/analysis/inventory provenance
  tracing, bounded regular-member enumeration, exact count/byte reconciliation, scan-error-region
  rejection, and explicit false content-read/execution/archive/removal authorization fields.
- Enrichment-evidence fusion implemented: full analysis/enrichment logical validation, exact
  session and inventory binding, D2 candidate versus D3/D4 confirmed separation, and directory
  coverage/member features with explicit denominators.
- Longitudinal analytics implemented: two-snapshot logical validation, metadata-only file changes,
  error-aware ambiguity, directory churn/byte deltas, temporal project nodes, contextual graph
  edges, components, and explicit zero dependency-evidence coverage.
- Explicit dependency-evidence analytics implemented: strict longitudinal and canonical-manifest
  validation, evaluated-project coverage, typed project relationships, deterministic dependency
  degrees, weighted degrees, PageRank-style centrality, components, and component-split risk.
- Multi-snapshot history implemented: canonical contiguous-chain manifests, independent
  longitudinal table/digest validation, ordinal file observation and stability, directory churn,
  project activity, and explicit non-value/non-action semantics.
- Multi-evidence review synthesis implemented: exact ranking/fusion/dependency/history lineage,
  independently recomputed logical table digests, candidate-level separated evidence dimensions,
  and named review signals without score/rank mutation or action semantics.
- Rootwise namespace migration implemented: distribution, packages, commands, schema identifiers,
  artifacts, GUI labels, documentation, and tooling use the Rootwise name with no legacy aliases.
- Acceptance evidence evaluation implemented: canonical manifests and deterministic reports cover
  million-entry resource budgets, recovery and corruption behavior, metadata edge cases,
  distinct-volume enrichment, visible GUI review, and independent reproduction. Missing gates are
  `INCOMPLETE`; supplied failures are `FAIL`; producer identities and evidence bytes remain
  unauthenticated external claims.
- Guided acceptance workflow implemented: deterministic evidence-empty manifest initialization,
  machine-readable required-measurement guidance, backward-compatible evaluation, and canonical
  report inspection with digest, complete-gate-set, per-gate semantic, and aggregate-status
  recomputation. Initialization deliberately cannot create a passing evidence claim.
- Immutable acceptance recording implemented: external evidence is stream-hashed, measurements
  require exact gate-specific canonical fields, and each command writes a new manifest revision.
  Output overwrite, path reuse, duplicate-gate replacement, and measurement field drift fail
  closed; computed negative evidence remains an explicit `FAIL`.
- Release-candidate admission implemented: a canonical complete `PASS` acceptance report is bound
  to its semantic digest, the verified source revision and manifest, exact source-archive SHA-256,
  build provenance, and successful fresh-extraction verification. Admission is refused for
  incomplete or failed evidence, lineage mismatch, malformed or tampered inputs, path reuse, and
  output overwrite. Receipts are deterministic and explicitly grant no filesystem execution
  authority; they do not authenticate evidence producers, sign or publish archives, or replace
  the nine real external gates.
- Admission-chain verification implemented: canonical receipt semantics and digest, complete
  acceptance status, revision lineage, exact archive identity, build provenance, and extraction
  verification are independently recomputed against all supplied artifacts. Noncanonical,
  tampered, mismatched, reused-path, and metadata-visibly changing inputs fail closed. Verification
  is read-only and grants no filesystem authority; it does not authenticate producers, establish a
  trusted timestamp, sign or publish archives, or turn incomplete external evidence into a pass.
- Concurrent-mutation revalidation implemented: each enumerated entry receives a fresh non-following
  metadata stat at observation time. Disappeared files and directories become structured errors,
  are not observed, and are not queued; stable siblings retain normal behavior. This remains a
  point-in-time inventory boundary rather than a stable handle or execution authorization.
- Scale-acceptance harness implemented: explicit clean-revision binding, operator budgets, new-only
  evidence outputs, metadata-only pre/post scanner manifests, current-process RSS and output-space
  sampling, query-only p95 measurement, and snapshot-pipeline orchestration. It creates no corpus,
  requires `--execute`, and emits `FAIL` rather than passing a sub-million fixture.
- Disposable scale-corpus preparation implemented: deterministic sharded zero-byte paths, an
  immutable ownership marker, bounded rate/batch controls, explicit stopping, exact-prefix resume,
  canonical queries and manifest, and no automatic cleanup. The million-entry corpus has not been
  created or measured; foreign or changed destinations fail closed.
- Tested locally: 131 synthetic/unit/static tests pass without warnings on CPython 3.14.3,
  including construction of the real PySide6 6.10.2 window using the offscreen Qt platform. Ruff
  and strict mypy pass across 67 source files under the hash-locked CPython 3.12 environment.
- GUI interaction and visual layout: the first visible 0.21 review found that persisted decisions
  were not distinguishable after recording; the next review exposed a theme-dependent white-on-
  white selection state. Stage 0.21a now uses explicit palette-safe recorded labels and adds the
  missing functional menu bar. The corrected surface then passed an operator-visible retest on the
  exact pre-merge 0.21a commit; final evidence must still be regenerated on the merged revision.
- Search scale: functionally tested with bounded pages and now has an opt-in measured gate harness;
  the million-entry campaign has not run and no Everything-performance claim is made.
- Analytics scale: deterministic fixture behavior is tested and now has an opt-in measured snapshot
  harness; multi-million-row memory, latency, and temporary-space behavior are not yet accepted.
- Ranking scale: deterministic fixture behavior is tested; cohort calibration, ranking stability
  under alternative uncertainty assumptions, and multi-million-row resource use are not accepted
  for the real source.
- Optimizer scale: exact frontier-state growth and small evolutionary fixtures are tested; large
  candidate trees, convergence quality, cross-seed variance, and thermal behavior are not accepted
  for the real source.
- Enrichment scale: only small synthetic selections are tested. D2/D3/D4 correctness, bounded
  stopping, duplicate status, unchanged file contents, and same-volume rejection are covered;
  large selections, throughput, thermal behavior, and hostile concurrent replacement are not
  accepted. Content reads may update access-time metadata depending on the filesystem.
- Approval scale: only small synthetic plan databases are tested. Plan tampering, declaration
  mismatch, candidate bounds, deterministic receipt output, and unchanged inputs are covered. The
  operator label is not authenticated, receipts are not digitally signed, and no executor consumes
  them.
- Preflight scale: only small synthetic inventories are tested. Provenance tampering, scan-error
  intersections, member bounds, count/byte reconciliation, deterministic output, and unchanged
  source contents are covered. Current source observations and destination capacity are not
  checked, and the output is intentionally non-executable.
- Fusion scale: only small synthetic D2/D3/D4 selections are tested. Evidence tampering, stopped
  runs, deterministic output, unchanged inputs/source contents, and candidate/confirmed separation
  are covered. Multi-million-row aggregation and combining multiple enrichment runs are not yet
  implemented or accepted.
- Longitudinal scale: only two small synthetic sessions are tested. Added, removed,
  metadata-changed, metadata-unchanged, error-ambiguous, project-added, contextual edge, unchanged
  input/source, and tampered-inventory behaviors are covered. Rename detection, automatic
  dependency extraction, and multi-million-row performance are not implemented or accepted in
  the individual transition stage; multi-snapshot aggregation is handled separately by 0.13.
- Dependency-evidence scale: only a small synthetic two-project declaration is tested. Canonical
  encoding, longitudinal/table tampering, unknown endpoints, explicit evaluated-project coverage,
  deterministic graph output, and unchanged inputs/source are covered. Rootwise does not
  generate or authenticate the supplied evidence, parse source manifests, or claim large-graph
  performance.
- History scale: only a synthetic three-snapshot/two-transition chain is tested. Contiguity,
  reversal, canonical encoding, table tampering, deterministic output, disappearance, repeated
  metadata change, stable transitions, and unchanged input/source behavior are covered. Timestamp
  duration, rename detection, long-chain resource use, and multi-million-path performance are not
  implemented or accepted.
- Synthesis scale: only a unified synthetic three-snapshot chain with D3 evidence and two projects
  is tested. Logical tampering, wrong analysis lineage, exact directory/project joins, separate
  evidence fields, dimension signals, deterministic output, and unchanged inputs/source are
  covered. Partial or optional evidence inputs, signal calibration, large candidate sets, and
  multi-million-row performance are not implemented or accepted.
- Acceptance-report scale: the evaluator is tested with synthetic complete, failed, incomplete,
  noncanonical, unknown-gate, duplicate-path, and over-budget declarations. The merged 0.21
  campaign recorded three local gates, but no million-entry run, corrected visible GUI review,
  distinct-volume enrichment acceptance, or independent replication has completed the full set;
  current real-world status therefore remains `INCOMPLETE`, not `PASS`.
- Release-admission scale: only small synthetic complete and incomplete acceptance reports and a
  synthetic source archive are tested. Determinism, exact archive hashing, unchanged inputs,
  report tampering, revision mismatch, failed extraction verification, path reuse, and output
  overwrite are covered. No real admission receipt has been issued because the retained real
  acceptance report is `INCOMPLETE`; archive signatures, producer authentication, publication,
  and execution remain outside this stage.
- Metadata-edge campaign: a real 371-character Windows path was fully observed; a real temporary
  `LIST_DIRECTORY` ACL denial produced structured evidence and was restored; injected invalid
  metadata produced a structured `EINVAL`; and deterministic file deletion after enumeration
  produced `FileNotFoundError` rather than a stale observation. File and directory deletion
  variants retain stable sibling observations. The merged 0.21 campaign recorded this and two
  other local gates as passing; because acceptance evidence is revision-bound, the campaign must
  restart after the corrective 0.21a revision is finalized.
- Admission-verification scale: only small synthetic admission chains are tested. Deterministic
  read-only verification, canonical and semantic receipt tampering, changes to every bound artifact,
  exact archive mismatch, and path reuse are covered. Concurrent archive mutation is detected when
  filesystem identity, size, or modification time changes during hashing. Digital signatures,
  trusted timestamps, producer authentication, and a real complete acceptance chain remain outside
  this stage.
- Installed analytics integration: passed against the retained 30-observation synthetic exFAT
  inventory after VHDX detachment, producing 15 roles, 16 aggregate nodes, one project, six
  relationships, and four `COMPLETE` stages while leaving the inventory byte-identical. Output
  digest: `7f600018bf172c3d7f2da2b39ea0af97749868fa8da6fa3232a2b8e444f935d1`.
- Installed ranking integration: passed against that retained 0.4 analysis using DuckDB 1.5.5,
  Polars 1.43.2, and PyArrow 25.0.0, producing 15 candidates, 60 objective intervals, six cohorts,
  and four `COMPLETE` stages. The analysis remained SHA-256
  `c1481ef4af56c1c0baa1d5c2e75193c0e944650db708c9712cf04ee80e6591fe`; ranking output digest:
  `cd1c173b8ecb6131775dcc2426f3cc14e0291b3217957bfa3343c744b02ffb7b`.
- Installed optimizer integration: passed against the retained detached synthetic snapshot using
  NumPy 2.4.6, SciPy 1.17.1, and pymoo 0.6.2. Fifteen candidates included two explicitly eligible
  and two protected groups; all six stages completed and 12 independently validated plans remained
  `UNAPPROVED`. R-NSGA-III encountered a zero-width objective range and its output was discarded in
  favor of the recorded degenerate fallback. Ranking SHA-256 remained
  `252e73caf0130412d24dad24ec513e1fc4b7f55a0dae2d16e2988a28cd802115`; plans output digest:
  `536d417d7c286dbe9a2169a99cb09ec0ee5e1f9bc2b378f24e29bfb55fac38ba`.
- Installed enrichment boundary: the 0.7 package and `rootwise-enrich` entry point are installed
  with BLAKE3 1.0.9. Synthetic D2/D3/D4 success paths pass only through an explicitly injected
  test volume resolver. The production resolver refuses a same-volume source/evidence setup before
  creating evidence or reading selected content. No distinct mounted disposable source is
  currently available for a successful installed-CLI content-read acceptance run.
- Installed approval integration: the `rootwise-approve` entry point completed a temporary
  synthetic plan-selection export, independently revalidated an archive-bearing proposal, left the
  plans database and declaration SHA-256-identical, and emitted a receipt with all three action
  authorizations false. This did not open source content or create an archive.
- Installed preflight integration: `rootwise-preflight` traced that same temporary approval
  through the synthetic plan, ranking, analysis, and inventory; enumerated and reconciled the
  archive members; left all inputs and source contents SHA-256-identical; and emitted four false
  authorization fields. No archive or destination artifact other than the manifest was created.
- Installed fusion integration: `rootwise-fuse-evidence` validated temporary D3 evidence,
  preserved three selected files as zero candidate and two confirmed duplicate members at the
  root, and left the inventory, analysis, evidence, and synthetic source contents SHA-256-identical.
  The successful installed run used the unlocked CPython 3.12 environment because an operator-open
  viewer held the CPython 3.14 console executable during the initial editable-install attempt.
- Installed longitudinal integration: `rootwise-longitudinal` compared two temporary complete
  snapshots and produced two additions, one removal, one metadata change, 13 metadata-unchanged
  observations, one contextual project edge, and zero dependency-evidence coverage while leaving
  all inputs and current synthetic source contents SHA-256-identical.
- Installed dependency integration: `rootwise-dependency-graph` consumed a canonical manifest
  bound to a temporary complete longitudinal run, imported one explicit directed `DEPENDS_ON`
  edge across two evaluated projects, reported coverage 1.0, and left the inventory,
  longitudinal database, manifest, and source contents SHA-256-identical.
- Installed history integration: `rootwise-history` consumed two contiguous temporary
  longitudinal runs representing three snapshots, recorded two metadata changes for a retained
  source path and a `NOT_OBSERVED` current state for one removed path, and left the inventory, chain
  manifest, longitudinal inputs, and source contents SHA-256-identical.
- Installed synthesis integration: `rootwise-synthesize-evidence` joined a temporary ranking,
  D3 fusion, explicit dependency graph, and three-snapshot history sharing one current analysis;
  emitted confirmed-duplicate and churn signals while leaving every input and source content
  SHA-256-identical.
- CPython 3.14 installation recovery: after the operator closed the viewer, the 0.11 editable
  install restored every console entry point. Stale 0.9 metadata from the interrupted uninstall was
  moved—not deleted—to `.tool-tmp/stale-install-quarantine`; `pip show` now reports 0.11.0a0 without
  the invalid-distribution warning.
- Windows acceptance: passed locally on Windows 10 Home for rewritten source commit `2aeae1e`; this was not
  an independent build or replication.
- exFAT VHDX: passed using a new 512 MiB disposable VHDX resolved only from its exact workspace
  image path. The retained VHDX was verified detached after the test.
- OS-enforced read-only: passed on the disposable exFAT volume. Cancellation produced `STOPPED`,
  resume reached `COMPLETE` in the same session, and pre/post content manifests were identical.
- Independent replication: not tested.
- Real 3.9+ TB source: not tested and remains prohibited pending an explicit minimum-evidence
  review and operator decision.

Expected Windows CPython 3.12 corpus digest:
`7a40e32dfa0ed16afab2ef42944db845daad3bf1477e07cd1061bbb8dbfec6b8`.

The platform-specific exFAT acceptance export contained 35 records with SHA-256
`c4cf55664a0c1e995b113daf18f5f6cac879c08473c0770602913bd582a87d49`. Its pre/post source
manifest SHA-256 was
`897f58e93e0f8645728da03c39fe61df5f05c8b4b9f375a731a25cf0b8ad0cb4`.
