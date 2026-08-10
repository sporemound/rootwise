from __future__ import annotations

from pathlib import Path

import pytest

from rootwise.database import InventoryDatabase
from rootwise.errors import ResourceLimitExceeded
from rootwise.models import ScanConfig, SessionState
from rootwise.resources import ResourceController, ResourcePolicy
from rootwise.scanner import MetadataScanner

from .helpers import RecordingGuard, actual_volume


def test_resource_controller_rejects_rss_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rootwise.resources.process_rss_bytes", lambda: 101)
    monkeypatch.setattr("rootwise.resources.destination_free_bytes", lambda _path: 10_000)
    controller = ResourceController(tmp_path, ResourcePolicy(100, 1, 30, 0), lambda: False)
    with pytest.raises(ResourceLimitExceeded, match="RSS"):
        controller.check()


def test_resource_controller_cooldown_is_bounded_and_interruptible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [0.0]
    sleeps: list[float] = []
    monkeypatch.setattr("rootwise.resources.process_rss_bytes", lambda: 1)
    monkeypatch.setattr("rootwise.resources.destination_free_bytes", lambda _path: 10_000)

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    controller = ResourceController(
        tmp_path, ResourcePolicy(100, 1, 1.0, 0.6), lambda: False,
        clock=lambda: now[0], sleeper=sleep,
    )
    controller.check()
    now[0] = 1.0
    controller.check()
    assert sleeps == [0.25, 0.25, pytest.approx(0.1)]


def test_resource_boundary_stops_session_with_structured_event(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "item.txt").touch()
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(
        str(source), str(database_path), 100_000, 2, 0,
        max_rss_mib=None, min_free_destination_mib=None,
    )

    class StopController:
        def check(self) -> None:
            raise ResourceLimitExceeded("synthetic resource boundary")

    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, state = MetadataScanner(
            source, actual_volume(source), database, config,
            resource_controller=StopController(),  # type: ignore[arg-type]
        ).run()
        assert state is SessionState.STOPPED
        assert database.connection.execute(
            "SELECT operation FROM scan_errors WHERE scan_session_id=?", (session,)
        ).fetchone()[0] == "resource_check"
        events = [row[0] for row in database.connection.execute(
            "SELECT event_type FROM scan_events WHERE scan_session_id=? ORDER BY event_id", (session,)
        )]
        assert events == ["STARTED", "RESOURCE_STOP", "STOPPED"]

