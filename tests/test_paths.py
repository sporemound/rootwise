from __future__ import annotations

import math
import os

import pytest

from paretodrive.models import ScanConfig
from paretodrive.scanner import inventory_path


def test_platform_separator_normalization_preserves_valid_name_meaning() -> None:
    value = inventory_path(r"folder\literal.txt")
    if os.name == "nt":
        assert value == "folder/literal.txt"
    else:
        assert value == r"folder\literal.txt"


def test_nonfinite_scan_rate_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        ScanConfig("source", "database", math.nan).validate()
