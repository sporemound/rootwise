# Rootwise

**Audit-first filesystem inventory and evidence-based storage planning for large, disorganized data collections.**

Rootwise is a local-first tool for understanding the structure, value, redundancy, and archival potential of a filesystem without beginning from a deletion workflow.

It combines:

- a bounded metadata-only scanner;
- an external SQLite inventory;
- a query-only review interface;
- structural and project analysis;
- uncertainty-aware Pareto ranking;
- proposal-only archive planning;
- explicitly permissioned content enrichment;
- evidence-based acceptance and release tooling.

Rootwise is being developed initially for a 3.9+ TB exFAT drive containing years of creative projects, software environments, media, research material, renders, downloads, archives, and probable duplicates.

> **Current status: `0.23.0-alpha`**
>
> Rootwise remains an unreleased development milestone. It is not yet approved for use against irreplaceable production data or the original 3.9+ TB source drive.

## What problem does Rootwise address?

Ordinary disk analyzers can tell you which folders are large. They generally cannot explain the difference between:

- a large cache that can be rebuilt;
- a unique source recording;
- an inactive but complete project;
- a small configuration file required to reconstruct hundreds of gigabytes;
- an exact duplicate;
- a same-size file that only appears duplicated;
- a coherent archive candidate;
- an uncertain folder that needs human review.

Rootwise keeps these dimensions separate rather than assigning one opaque “importance score.”

Typical analytical dimensions include:

```text
uniqueness
rebuildability
project relevance
archival value
dependency risk
storage cost
duplicate evidence
structural coherence
uncertainty
