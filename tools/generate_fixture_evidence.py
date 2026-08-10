"""Generate one canonical inventory from the deterministic synthetic corpus."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rootwise.canonicalize import export_canonical
from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig
from rootwise.scanner import MetadataScanner
from tests.helpers import RecordingGuard, actual_volume, make_corpus


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rootwise-fixture-") as temporary:
        root = Path(temporary)
        source = make_corpus(root / "source")
        database_path = root / "inventory.db"
        output = root / "inventory.ndjson"
        config = ScanConfig(str(source), str(database_path), 1_000_000, 7, 0)
        guard = RecordingGuard(root)
        with InventoryDatabase(database_path, guard) as database:
            session, state = MetadataScanner(source, actual_volume(source), database, config).run()
            digest, records = export_canonical(database, guard, session, output)
        print(json.dumps({"sha256": digest, "records": records, "state": state.value}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
