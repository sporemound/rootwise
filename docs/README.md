# Rootwise Documentation Index

This index is the single entry point for detailed Rootwise documentation. A new contributor should
read only the three primary documents before coding:

1. [README.md](../README.md) — product purpose, capabilities, status, and limitations.
2. [ARCHITECTURE.md](../ARCHITECTURE.md) — components, data flow, artifacts, and trust boundaries.
3. [DEVELOPMENT.md](../DEVELOPMENT.md) — installation, tests, synthetic workflows, and contribution
   rules.

Consult the documents below only for the subsystem being changed. The archive preserves provenance
but is not part of the current developer path.

## Classification

- **Active reference:** current design, schema, boundary, or developer guidance.
- **Protocol:** an explicit operational or validation procedure whose prerequisites and safety
  checks matter.
- **Historical:** a point-in-time result, review, migration, or status record retained for context.
- **Redundant:** original material retained verbatim after its active content was consolidated into
  a responsibility-based document.

No L3 source document was deleted. Five overlapping acceptance/release documents were consolidated
into two active protocols; their originals remain under `archive/`.

## Root entry points

| Document | Classification | Purpose |
|---|---|---|
| [README.md](../README.md) | Active reference | Product landing page and current limits |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Active reference | Canonical target architecture and authority model |
| [DEVELOPMENT.md](../DEVELOPMENT.md) | Active reference | Cold-start contributor workflow |
| [SECURITY.md](../SECURITY.md) | Active reference | Security reporting and review entry point |
| [CHANGELOG.md](../CHANGELOG.md) | Historical | Release chronology and implementation record |
| [LICENSE](../LICENSE) | Active reference | MIT license terms |

## Architecture and product behavior

| Document | Classification | Purpose |
|---|---|---|
| [Repository map](architecture/repository-map.md) | Active reference | Factual pre-refactor packages, commands, imports, artifacts, and maturity |
| [Database schema](architecture/database-schema.md) | Active reference | Core inventory tables and state |
| [Decision schema](architecture/decision-schema.md) | Active reference | Separate revisioned user-decision storage |
| [Viewer experience](architecture/viewer-experience.md) | Active reference | Approved ordinary inventory-browser behavior and capability classes |
| [View modes](architecture/view-modes.md) | Active reference | Details, compact, and deferred tile presentation contracts |
| [Keyboard and navigation](architecture/keyboard-and-navigation.md) | Active reference | Inventory-only navigation, shortcuts, and context actions |
| [Accessibility](architecture/accessibility.md) | Active reference | Focus, roles, contrast, high-DPI, latency, and review expectations |

## Safety

| Document | Classification | Purpose |
|---|---|---|
| [Safety invariants](safety/safety-invariants.md) | Active reference | Normative scanner requirements and prohibited capabilities |
| [Threat model](safety/threat-model.md) | Active reference | Assets, attackers, boundaries, controls, and residual risk |
| [Filesystem capabilities](safety/filesystem-capabilities.md) | Active reference | Portable, Windows, POSIX, and exFAT capability differences |
| [Concurrent mutation](safety/concurrent-mutation.md) | Active reference | Point-in-time observation and mutation race boundary |
| [Viewer boundary](safety/viewer-boundary.md) | Active reference | Query-only inventory and separate decision-store guarantees |
| [Analysis boundary](safety/analysis-boundary.md) | Active reference | Snapshot-only structural-analysis guarantees |

## Analytics and evidence

| Document | Classification | Purpose |
|---|---|---|
| [Analytics schemas](analytics/analytics-schema.md) | Active reference | Derived databases and canonical artifact schemas |
| [Ranking](analytics/ranking.md) | Active reference | Objective intervals, Pareto fronts, and review queues |
| [Enrichment evidence](analytics/evidence-enrichment.md) | Active reference | Separately permissioned bounded content hashing |
| [Evidence fusion](analytics/evidence-fusion.md) | Active reference | Validation and fusion of structural and content evidence |
| [Temporal analysis](analytics/temporal-analysis.md) | Active reference | Two-snapshot change and relationship semantics |
| [Dependency evidence](analytics/dependency-evidence.md) | Active reference | Explicit dependency declarations and graph features |
| [History](analytics/history.md) | Active reference | Multi-snapshot chain and temporal feature semantics |
| [Synthesis](analytics/synthesis.md) | Active reference | Lineage-bound multi-evidence review signals |

## Planning

| Document | Classification | Purpose |
|---|---|---|
| [Optimization](planning/optimization.md) | Active reference | Proposal-only exact and evolutionary search contract |
| [Approval](planning/approval.md) | Active reference | Independent selected-plan receipt and non-authority flags |
| [Preflight](planning/preflight.md) | Active reference | Metadata-only proposal-member compilation |

## Validation

| Document | Classification | Purpose |
|---|---|---|
| [Acceptance](validation/acceptance.md) | Protocol | Consolidated gates, manifest recording, evaluation, and inspection workflow |
| [Release admission](validation/release-admission.md) | Protocol | Verification, source packaging, admission, and read-only chain verification |
| [Scale acceptance](validation/scale-acceptance.md) | Protocol | Scanner, viewer-search, and snapshot-pipeline measurement harness |

## Protocols

| Document | Classification | Purpose |
|---|---|---|
| [Testing](protocols/testing.md) | Protocol | Local mandatory and external platform gates |
| [Replication](protocols/replication.md) | Protocol | Fresh-clone, cross-host deterministic comparison |
| [Disposable VHDX](protocols/disposable-vhdx.md) | Protocol | Windows exFAT virtual-disk preparation and retention boundary |
| [Scale corpus](protocols/scale-corpus.md) | Protocol | New-only million-entry synthetic corpus preparation |

## Archive

Archived documents are preserved for provenance. They may describe stale package names, historical
results, or component-era versions and must not override active architecture, safety, or validation
documents.

| Document | Classification | Superseded by or retained for |
|---|---|---|
| [Acceptance contract 0.16](archive/acceptance-contract-0.16.md) | Redundant | Consolidated [acceptance protocol](validation/acceptance.md) |
| [Acceptance workflow 0.17](archive/acceptance-workflow-0.17.md) | Redundant | Consolidated [acceptance protocol](validation/acceptance.md) |
| [Acceptance recording 0.18](archive/acceptance-recording-0.18.md) | Redundant | Consolidated [acceptance protocol](validation/acceptance.md) |
| [Release admission 0.19](archive/release-admission-0.19.md) | Redundant | Consolidated [release protocol](validation/release-admission.md) |
| [Admission verification 0.20](archive/admission-verification-0.20.md) | Redundant | Consolidated [release protocol](validation/release-admission.md) |
| [Audit.2 acceptance result](archive/audit2-acceptance-result.md) | Historical | Point-in-time local Windows/exFAT result |
| [Developer review notes](archive/developer-review-notes.md) | Historical | Early architectural review inputs |
| [Namespace migration 0.15](archive/namespace-migration-0.15.md) | Historical | Completed product rename record |
| [Release status 0.23](archive/release-status-0.23.md) | Historical | Detailed point-in-time implementation and evidence snapshot |
| [Security review Audit.2](archive/security-review-audit2.md) | Historical | Point-in-time findings and assumptions; later results may differ |

When an active document changes meaning, update its contract and tests together. Add historical
results to `CHANGELOG.md` or the archive instead of expanding the primary reading path.
