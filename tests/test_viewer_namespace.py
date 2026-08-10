from __future__ import annotations

import rootwise_view
from rootwise import viewer
from rootwise_view import cli as compatibility_cli
from rootwise_view import decisions as compatibility_decisions
from rootwise_view import inventory as compatibility_inventory


def test_compatibility_package_reexports_canonical_viewer_api() -> None:
    assert rootwise_view.InventoryReader is viewer.InventoryReader
    assert rootwise_view.DecisionStore is viewer.DecisionStore
    assert compatibility_inventory.InventoryReader is viewer.InventoryReader
    assert compatibility_decisions.DecisionStore is viewer.DecisionStore


def test_compatibility_cli_reexports_canonical_entry_point() -> None:
    from rootwise.viewer import cli as canonical_cli

    assert compatibility_cli.main is canonical_cli.main
    assert compatibility_cli.parser is canonical_cli.parser
