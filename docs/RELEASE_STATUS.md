# Release Status

Version: `0.7.0-alpha` (unreleased source milestone)

- Designed: metadata-only scanner boundary and staged release gates.
- Implemented: volume identity, guarded outputs, handle-bound traversal, SQLite sessions,
  cancellation/resume, structured errors, and deterministic canonical export.
- Viewer implemented: query-only inventory reader, bounded search, separate revisioned decisions,
  headless CLI, and optional PySide6 table interface.
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
- Tested locally: 58 synthetic/unit/static tests pass without warnings on CPython 3.14.3,
  including construction of the real PySide6 6.10.2 window using the offscreen Qt platform. Ruff
  and strict mypy pass across 37 source files under the hash-locked CPython 3.12 environment.
- GUI interaction and visual layout: constructed and event-processed offscreen; not yet manually
  reviewed in a visible desktop session.
- Search scale: functionally tested with bounded pages; not benchmarked at millions of rows and
  not an Everything-performance claim.
- Analytics scale: deterministic fixture behavior is tested; multi-million-row memory, latency,
  and temporary-space behavior are not benchmarked or accepted for the real source.
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
- Installed enrichment boundary: the 0.7 package and `paretodrive-enrich` entry point are installed
  with BLAKE3 1.0.9. Synthetic D2/D3/D4 success paths pass only through an explicitly injected
  test volume resolver. The production resolver refuses a same-volume source/evidence setup before
  creating evidence or reading selected content. No distinct mounted disposable source is
  currently available for a successful installed-CLI content-read acceptance run.
- Windows acceptance: passed locally on Windows 10 Home for source commit `018435d`; this was not
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
