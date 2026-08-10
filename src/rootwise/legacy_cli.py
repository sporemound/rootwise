"""Compatibility console-script wrappers for the pre-consolidation CLI names."""

from __future__ import annotations

import sys


def _notice(old: str, new: str) -> None:
    print(
        f"DEPRECATION: '{old}' is retained as a compatibility alias; use '{new}'.",
        file=sys.stderr,
    )


def view() -> int:
    _notice("rootwise-view", "rootwise view")
    from .viewer.cli import main

    return main()


def analyze() -> int:
    _notice("rootwise-analyze", "rootwise analyze structural")
    from rootwise_analytics.cli import main

    return main()


def rank() -> int:
    _notice("rootwise-rank", "rootwise analyze rank")
    from rootwise_analytics.ranking_cli import main

    return main()


def optimize() -> int:
    _notice("rootwise-optimize", "rootwise plan optimize")
    from rootwise_analytics.optimizer_cli import main

    return main()


def enrich() -> int:
    _notice("rootwise-enrich", "rootwise evidence enrich")
    from rootwise_enrich.cli import main

    return main()


def approve() -> int:
    _notice("rootwise-approve", "rootwise plan approve")
    from rootwise_approval.cli import main

    return main()


def preflight() -> int:
    _notice("rootwise-preflight", "rootwise plan preflight")
    from rootwise_preflight.cli import main

    return main()


def fuse() -> int:
    _notice("rootwise-fuse-evidence", "rootwise analyze fuse")
    from rootwise_fusion.cli import main

    return main()


def temporal() -> int:
    _notice("rootwise-longitudinal", "rootwise analyze temporal")
    from rootwise_longitudinal.cli import main

    return main()


def dependency() -> int:
    _notice("rootwise-dependency-graph", "rootwise evidence dependency")
    from rootwise_dependency.cli import main

    return main()


def history() -> int:
    _notice("rootwise-history", "rootwise evidence history")
    from rootwise_history.cli import main

    return main()


def synthesize() -> int:
    _notice("rootwise-synthesize-evidence", "rootwise analyze synthesize")
    from rootwise_synthesis.cli import main

    return main()


def acceptance() -> int:
    _notice("rootwise-acceptance", "rootwise verify acceptance")
    from rootwise_acceptance.cli import main

    return main()
