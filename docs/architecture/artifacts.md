# Artifact Catalog

Rootwise commands accept explicit paths; the basenames below are conventions, not implicit output
locations. A command never searches for one of these names, silently reuses an existing artifact,
or derives authority from a filename. Persisted application and schema identities remain the
authoritative type checks.

Use one artifact directory per synthetic run or review campaign. Do not overwrite a completed
artifact to make it represent a later run. Where a workflow supports revision, write a new file
and retain its bound predecessor.

## SQLite artifacts

| Recommended basename | Application ID | Producer | Primary readers | Lifecycle | Source observations | User decisions | Filesystem execution authority |
|---|---:|---|---|---|---|---|---|
| `inventory.db` | `1346654806` | Core scanner | Viewer, Analysis, Evidence, Planning preflight | Mutable only during scan/resume; snapshot after `COMPLETE` | Raw metadata and errors | No | None |
| `decisions.db` | `1346654807` | Viewer | Viewer and Planning | Revision-checked mutable state with append-only history | Inventory-relative references only | Yes | None |
| `analysis.db` | `1346654808` | Structural Analysis | Ranking, temporal/fused analysis, Planning | Newly derived; completed run consumed immutably | Derived observations | No | None |
| `ranking.db` | `1346654809` | Ranking Analysis | Planning and review-signal synthesis | Newly derived; completed run consumed immutably | Derived scores/fronts | No | None |
| `plans.db` | `1346654810` | Planning optimizer | Approval and preflight review | Newly derived proposals; every proposal begins unapproved | Derived group references | Input digest only | None |
| `content-evidence.db` | `1346654811` | Permissioned Evidence enrichment | Fused Analysis | Newly derived and immutable | Selected paths and content digests | No | None |
| `fused-analysis.db` | `1346654812` | Fused Analysis | Review-signal synthesis | Newly derived; completed run consumed immutably | Derived evidence features | No | None |
| `temporal-analysis.db` | `1346654813` | Temporal Analysis | Dependency Evidence and History | Newly derived comparison | Derived changes | No | None |
| `dependency-evidence.db` | `1346654814` | Dependency Evidence | Review-signal synthesis | Newly derived and immutable | Project references | No | None |
| `history.db` | `1346654815` | History Evidence | Review-signal synthesis | Newly derived and immutable | Derived multi-snapshot observations | No | None |
| `review-signals.db` | `1346654816` | Review-signal Analysis | Human review and future Viewer integration | Newly derived terminal review artifact | Derived signals | No | None |

The older example names `evidence.db`, `fusion.db`, `longitudinal.db`, `dependency.db`, and
`synthesis.db` remain valid user-supplied paths. They are no longer the recommended names because
they require component-era context to interpret. No database was renamed in place and no schema or
application ID changed.

## Workflow JSON and stream artifacts

| Recommended basename | Persisted identity | Producer | Primary readers | Lifecycle and authority |
|---|---|---|---|---|
| `inventory.ndjson` | Canonical inventory record stream | Core canonical exporter | Replication and comparison tools | Immutable export; no authority |
| `content-selection.json` | `rootwise-enrichment-selection-1` | Operator or selection builder | Permissioned Evidence enrichment | Immutable, bounded content-read request; no write/execution authority |
| `dependency-evidence.json` | `rootwise-project-dependency-evidence-v1` | External evidence producer | Dependency Evidence | Immutable declared relationships; no authority |
| `history-chain.json` | `rootwise-longitudinal-chain-v1` | Operator or validation workflow | History Evidence | Immutable ordered snapshot chain; no authority |
| `plan-approval-declaration.json` | `rootwise-plan-approval-declaration-1` | Operator | Planning approval | Immutable intent input; does not itself approve or execute anything |
| `plan-approval-receipt.json` | `rootwise-plan-approval-receipt-1` | Planning approval | Planning preflight and human review | Immutable selection/revalidation record; every action authorization is false |
| `preflight-manifest.json` | `rootwise-executor-preflight-manifest-1` | Planning preflight | Human review and any separately designed future executor | Immutable metadata-only member list; every action authorization is false |
| `acceptance-evidence.json` | `rootwise-acceptance-evidence-v1` | Validation workflow | Acceptance evaluator | Revisioned by writing a new canonical file; readiness evidence only |
| `acceptance-report.json` | `rootwise-acceptance-report-v1` | Acceptance evaluator | Human review and release admission | Immutable evaluation; `PASS` is not execution authority |
| `release-admission.json` | `rootwise-release-admission-v1` | Release admission | Admission verifier | Immutable release-chain receipt; filesystem execution remains false |
| `.rootwise-scale-corpus.json` | `rootwise-scale-corpus-v1` | Scale-corpus preparer | Resume and ownership validation | Immutable ownership marker for one disposable corpus; no authority outside that corpus |
| `corpus-manifest.json` | `rootwise-scale-corpus-manifest-v1` | Scale-corpus preparer | Scale acceptance and human review | Immutable corpus metadata; no authority |
| `<gate>-scale-evidence.json` | `rootwise-scale-evidence-v1` | Scale-acceptance harness | Acceptance recorder and human review | Immutable measured-command evidence; no authority |
| `<gate>-scale-measurements.json` | Gate-specific fields from `rootwise verify acceptance guide` | Scale-acceptance harness | Acceptance recorder | Immutable measurements; no authority |

Gate evidence and measurements are external inputs rather than Rootwise application artifacts.
Use `<gate>-evidence.json` and `<gate>-measurements.json` so their role is visible beside an
acceptance manifest. The scale-corpus query suite uses `viewer-queries.json`; its canonical bounded
list format is validated separately from the corpus manifest.

## Repository verification and release artifacts

Repository tooling writes these exact names beneath `artifacts/`:

| Name or pattern | Producer | Purpose | Authority |
|---|---|---|---|
| `SOURCE_MANIFEST.json` | `tools/verify.py` | Bind tracked source bytes | None |
| `TEST-WINDOWS.json`, `TEST-LINUX.json`, `TEST-EXFAT-VHDX.json`, `TEST-READ-ONLY.json` | Verification procedures | Record platform-specific status | None |
| `SAFETY-AUDIT.json` | `tools/verify.py` | Record mandatory safety-test status | None |
| `BUILD_PROVENANCE.json` | `tools/verify.py` | Bind revision, environment, and source manifest | None |
| `SBOM.json` | `tools/verify.py` | Record installed distribution inventory | None |
| `SHA256SUMS.txt` | `tools/verify.py` | Transport hashes for verification artifacts | None |
| `rootwise-<version>-source.zip` | `tools/build_release.py` | Deterministic source distribution | None |
| `VERIFY-RELEASE.json` | `tools/verify_release.py` | Record fresh-extraction verification | None |

Hashes establish identity and lineage, not truth, safety, producer authenticity, permission to read
source contents, or authority to move, archive, replace, or delete files.
