# 0.15 Rootwise Namespace Migration

Stage 0.15 changes the complete product-facing namespace to Rootwise. This is an intentional
alpha-stage compatibility break, not an alias layer.

## Renamed surfaces

- Python distribution: `rootwise`
- Python packages: `rootwise` and `rootwise_*`
- Console entry points: `rootwise` and `rootwise-*`
- Manifest and receipt schema identifiers: `rootwise-*`
- Test environment variable: `ROOTWISE_ENTRYPOINT_DIR`
- Release archives and temporary prefixes: `rootwise-*`
- GUI title, CLI program names, documentation, license attribution, and examples

SQLite application IDs remain unchanged so existing database types are still recognizable.
However, databases that record absolute paths must still satisfy the existing sibling-path and
lineage checks after a checkout or artifact move.

## Compatibility boundary

There are no legacy import or command aliases in 0.15. Canonical JSON declarations, selections,
receipts, and chain manifests created with a pre-0.15 schema identifier must be regenerated with
the Rootwise schema identifier before use.

The D2 sampled-fingerprint domain separator is also renamed. D2 is candidate evidence only, and
pre-0.15 D2 values must not be compared with 0.15 D2 values. D3 full BLAKE3 and D4 SHA-256 remain
algorithmically unchanged, but their enclosing manifests and provenance must use the 0.15 schema.

This migration adds no source access, archive, move, rename, delete, network, approval, optimizer,
or execution authority. The source-facing safety boundaries remain unchanged.

