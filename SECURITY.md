# Rootwise Security

Rootwise is an unreleased alpha. No version is approved for irreplaceable production data, and the
real source-drive campaign remains prohibited while acceptance evidence is incomplete.

## Security model

Rootwise treats the observed filesystem as untrusted input and the operator-selected external
artifact directory as a trust boundary. Its primary security property is preservation: observing,
reviewing, analyzing, or planning must not mutate the source.

The current architecture enforces these capability separations:

- Core reads source metadata but not source-file contents.
- Viewer reads completed inventories query-only and writes decisions to a separate database.
- Analysis and Planning operate on recorded artifacts, not live source paths.
- Planning produces records with no filesystem execution authority.
- Content enrichment requires an explicit, immutable, bounded selection and separate permission.
- Validation evaluates evidence but does not authenticate its producer or authorize an action.
- No archive executor exists.

The normative implementation requirements are the
[safety invariants](docs/safety/safety-invariants.md). The
[threat model](docs/safety/threat-model.md) defines attacker capabilities, trust boundaries, and
residual risk. [ARCHITECTURE.md](ARCHITECTURE.md) explains how those boundaries map to components
and artifacts.

## Reporting a security issue

Do not attach inventories, decisions databases, filesystem listings, source-content evidence,
credentials, or private host details to a public issue. Report a suspected vulnerability to the
maintainer through a private GitHub channel for this repository. Include:

- the exact commit and platform;
- the component and command involved;
- a minimal synthetic reproducer;
- the expected and observed trust-boundary behavior; and
- whether any real source data may have been exposed or modified.

If private reporting is unavailable, open a minimal issue asking the maintainer to establish a
private channel without disclosing vulnerability details.

## Sensitive artifacts

Inventory and evidence artifacts can reveal names, directory structure, sizes, timestamps,
relationships, decisions, and—when explicitly enabled—content digests. Treat them as sensitive
local data even though they carry no execution authority. Keep them outside the source volume,
restrict access using operating-system controls, and do not commit generated artifacts unless they
are purpose-built synthetic fixtures.

Digest binding detects changes; it does not authenticate a person, host, or evidence producer.
Acceptance receipts are not signatures or trusted timestamps.

## Changes requiring focused review

Any change that adds or alters the following requires explicit threat-model and safety-invariant
review before merge:

- source traversal, path resolution, link handling, or volume identity;
- write destinations, overwrite behavior, SQLite journaling, or recovery state;
- source-content access or selection validation;
- subprocess, shell, network, archive, move, rename, copy, link, or deletion APIs;
- conversion of a decision, plan, receipt, or manifest into operational authority; or
- consolidation that lets a less privileged domain import a more privileged capability.

Structural cleanup must stop if it begins changing those semantics. Use synthetic fixtures and the
applicable [validation protocols](docs/README.md#protocols); do not use production data as a test.
