# Cold-Start Engineering Review

Status: **PASS** for Milestone L8's architecture-understanding exit condition.

Review baseline: `534a80a2ae3eee956ce1a66f6add00978f548033`

Review date: 2026-08-10

Review type: isolated automated cold-start engineering review. The reviewer was a separate Codex
agent with no prior project conversation or implementation-stage history. This is useful
legibility evidence, but it is not a human review, an independent-host replication, or a substitute
for the acceptance campaign.

## Review controls

The reviewer was instructed to read, in order:

1. `README.md`
2. `ARCHITECTURE.md`
3. `DEVELOPMENT.md`

Only then could the reviewer inspect source and focused tests as needed. The reviewer was barred
from `CHANGELOG.md`, `docs/archive/`, Git history, branches, pull requests, prior conversation, and
file edits. No explanations or corrections were supplied during the review. The reviewer ran no
tests.

## Required questions and independent answers

### 1. What does Rootwise do?

The reviewer described Rootwise as a local-first, audit-first storage-understanding system that
records a bounded resumable metadata inventory, supports query-only review and separate revisioned
decisions, derives deterministic evidence, and produces validated but non-executable proposals.
They correctly stated that Rootwise is not a file manager, archive tool, or executor and that an
artifact never confers filesystem authority.

Evidence cited by the reviewer: `README.md` lines 3–23 on the baseline and `ARCHITECTURE.md` lines
83–183.

### 2. What touches the source filesystem?

The reviewer identified three source-facing boundaries:

- Core path/volume authorization and capability inspection probe path and volume facts.
- The Core scanner enumerates directories and obtains non-following metadata without opening
  regular-file contents.
- Permissioned Evidence enrichment is the only ordinary production path that reads selected file
  contents, with explicit acknowledgement, immutable bounds, volume separation, and metadata
  revalidation.

They correctly distinguished guarded artifact writes and disposable validation tooling from
observed-source mutation, and stated that Viewer, Analysis, and Planning consume artifacts rather
than observed live paths.

Evidence cited: `src/rootwise/scanner.py`, `src/rootwise/volume.py`,
`src/rootwise/write_guard.py`, `src/rootwise/capabilities.py`, `src/rootwise_enrich/reader.py`,
`src/rootwise_enrich/pipeline.py`, and the related static-safety tests.

### 3. Where would you add a Viewer feature?

The reviewer selected `src/rootwise/viewer`, with query/navigation in `inventory.py`, decisions in
`decisions.py`, commands in `cli.py`, presentation in `gui.py`, and corresponding focused tests.
They explicitly rejected adding behavior to compatibility-only `src/rootwise_view`. They also kept
analysis derivation and permissioned content previews outside ordinary Viewer access.

### 4. Where would you add an analytics feature?

The reviewer selected the Analysis domain behind `rootwise analyze`, consuming completed artifacts
without source traversal. They correctly recognized the transitional implementation split across
`rootwise_analytics`, `rootwise_fusion`, `rootwise_longitudinal`, and `rootwise_synthesis`, and would
place a narrow change with its current stage rather than combining it with an opportunistic
namespace move.

### 5. Where would you add a Rust scanner?

The reviewer placed a hypothetical Rust scanner logically in Core behind `rootwise scan`, but
refused to choose a physical layout or integration mechanism without the separately required
architecture decision and measured justification. They noticed that launching a binary as a child
process would conflict with Core's current no-subprocess boundary unless that boundary were
explicitly redesigned.

### 6. What seems redundant or unclear?

The reviewer identified intentional compatibility duplication, the transitional top-level package
layout, optimizer code currently nested in `rootwise_analytics`, repeated artifact validation
patterns, and several documented future integrations. These observations match the repository's
current-versus-target architecture rather than inventing missing runtime behavior.

## Confusion log

The following points are preserved from the review without verbal explanation:

1. The architecture is prescriptive while the package layout remains transitional.
2. Analysis maps to several packages, while optimizer code shares `rootwise_analytics` despite
   belonging to Planning.
3. History ownership appeared inconsistent between Evidence and temporal Analysis descriptions.
4. The README said Planning could inspect proposals while Development and the CLI said no public
   inspection command exists.
5. Viewer may conceptually consume Analysis artifacts, but no current adapter implements that path.
6. Viewer owns presentation preferences conceptually, but no persistent preference store is
   evident.
7. The `verify` group label is broader than its single current `acceptance` operation suggests.
8. A Rust scanner's logical owner is clear, but its integration/distribution mechanism is not.
9. “Fourteen installed console scripts” required source inspection to resolve as one canonical
   command plus thirteen compatibility commands.

Items 3 and 4 exposed stale or inaccurate primary documentation and were corrected after the
baseline review. The remaining items are non-blocking transitional or future-work observations;
they are not presented as implemented capabilities.

## Contribution readiness

The reviewer answered **Yes**: they could begin a bounded Viewer query/presentation change or a
stage-local Analysis change using the primary documents, current code, and focused tests without
developer intervention. They correctly declined to begin a Rust scanner or other source-facing
capability without reading the required safety material and obtaining the required architecture
decision.

## Exit-condition assessment

**PASS — A technically experienced reviewer can correctly describe the architecture without
developer intervention.**

The reviewer reconstructed the component model, data flow, source-access boundaries, artifact
authority model, current-to-target package mapping, and known open decisions. Transitional package
fragmentation caused friction but did not prevent a correct description or a narrow contribution.

## Evidence limits and follow-up

- This was an isolated automated review, not a human usability study.
- Review duration against the aspirational 15–30 minute window was not measured.
- The reviewer used the same checkout and host and did not run commands or tests.
- L5 namespace consolidation remains incremental; top-level package fragmentation is still visible.
- A future human cold-start review should use the same three-document packet and record confusion
  before receiving explanations.
- A Rust implementation still requires a separate architecture decision; Viewer analysis adapters
  and preference persistence remain future product work.
