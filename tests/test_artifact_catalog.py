from __future__ import annotations

from pathlib import Path

from rootwise.viewer.decisions import DECISION_APPLICATION_ID
from rootwise.viewer.inventory import INVENTORY_APPLICATION_ID
from rootwise_acceptance.admission import ADMISSION_SCHEMA_ID
from rootwise_acceptance.evaluator import REPORT_SCHEMA_ID, SCHEMA_ID as ACCEPTANCE_SCHEMA_ID
from rootwise_analytics.optimizer_pipeline import PLAN_APPLICATION_ID
from rootwise_analytics.pipeline import ANALYSIS_APPLICATION_ID
from rootwise_analytics.ranking_pipeline import RANKING_APPLICATION_ID
from rootwise_approval.declaration import SCHEMA_VERSION as APPROVAL_DECLARATION_SCHEMA
from rootwise_approval.receipt import RECEIPT_SCHEMA_VERSION
from rootwise_dependency.pipeline import (
    DEPENDENCY_APPLICATION_ID,
    SCHEMA_ID as DEPENDENCY_SCHEMA_ID,
)
from rootwise_enrich.pipeline import ENRICHMENT_APPLICATION_ID
from rootwise_enrich.selection import SCHEMA_VERSION as ENRICHMENT_SELECTION_SCHEMA
from rootwise_fusion.pipeline import FUSION_APPLICATION_ID
from rootwise_history.pipeline import HISTORY_APPLICATION_ID, SCHEMA_ID as HISTORY_SCHEMA_ID
from rootwise_longitudinal.pipeline import LONGITUDINAL_APPLICATION_ID
from rootwise_preflight.compiler import SCHEMA_VERSION as PREFLIGHT_SCHEMA
from rootwise_synthesis.pipeline import SYNTHESIS_APPLICATION_ID
from tools.prepare_scale_corpus import CORPUS_SCHEMA, MANIFEST_SCHEMA
from tools.run_scale_acceptance import EVIDENCE_SCHEMA as SCALE_EVIDENCE_SCHEMA


SQLITE_IDENTITIES = {
    "inventory.db": INVENTORY_APPLICATION_ID,
    "decisions.db": DECISION_APPLICATION_ID,
    "analysis.db": ANALYSIS_APPLICATION_ID,
    "ranking.db": RANKING_APPLICATION_ID,
    "plans.db": PLAN_APPLICATION_ID,
    "content-evidence.db": ENRICHMENT_APPLICATION_ID,
    "fused-analysis.db": FUSION_APPLICATION_ID,
    "temporal-analysis.db": LONGITUDINAL_APPLICATION_ID,
    "dependency-evidence.db": DEPENDENCY_APPLICATION_ID,
    "history.db": HISTORY_APPLICATION_ID,
    "review-signals.db": SYNTHESIS_APPLICATION_ID,
}

JSON_IDENTITIES = {
    "content-selection.json": ENRICHMENT_SELECTION_SCHEMA,
    "dependency-evidence.json": DEPENDENCY_SCHEMA_ID,
    "history-chain.json": HISTORY_SCHEMA_ID,
    "plan-approval-declaration.json": APPROVAL_DECLARATION_SCHEMA,
    "plan-approval-receipt.json": RECEIPT_SCHEMA_VERSION,
    "preflight-manifest.json": PREFLIGHT_SCHEMA,
    "acceptance-evidence.json": ACCEPTANCE_SCHEMA_ID,
    "acceptance-report.json": REPORT_SCHEMA_ID,
    "release-admission.json": ADMISSION_SCHEMA_ID,
    ".rootwise-scale-corpus.json": CORPUS_SCHEMA,
    "corpus-manifest.json": MANIFEST_SCHEMA,
    "<gate>-scale-evidence.json": SCALE_EVIDENCE_SCHEMA,
}


def test_artifact_catalog_covers_persisted_identities_and_authority() -> None:
    root = Path(__file__).parents[1]
    catalog = (root / "docs" / "architecture" / "artifacts.md").read_text(encoding="utf-8")
    for filename, identity in {**SQLITE_IDENTITIES, **JSON_IDENTITIES}.items():
        assert f"| `{filename}` | `{identity}` |" in catalog
    assert catalog.count("Filesystem execution authority") == 1
    for filename in SQLITE_IDENTITIES:
        row = next(line for line in catalog.splitlines() if line.startswith(f"| `{filename}` |"))
        assert row.endswith("| None |")
    index = (root / "docs" / "README.md").read_text(encoding="utf-8")
    assert "[Artifact catalog](architecture/artifacts.md)" in index


def test_installed_fixture_generators_use_recommended_artifact_names() -> None:
    root = Path(__file__).parents[1]
    tool_names = (
        "generate_approval_evidence.py",
        "generate_dependency_evidence.py",
        "generate_fusion_evidence.py",
        "generate_longitudinal_evidence.py",
        "generate_synthesis_evidence.py",
    )
    sources = "\n".join((root / "tools" / name).read_text(encoding="utf-8") for name in tool_names)
    for filename in (
        "content-evidence.db",
        "fused-analysis.db",
        "temporal-analysis.db",
        "dependency-evidence.db",
        "review-signals.db",
        "plan-approval-declaration.json",
        "plan-approval-receipt.json",
    ):
        assert f'"{filename}"' in sources
    for former_name in (
        "evidence.db",
        "fusion.db",
        "longitudinal.db",
        "dependency.db",
        "synthesis.db",
        "approval-declaration.json",
        "approval-receipt.json",
    ):
        assert f'root / "{former_name}"' not in sources
