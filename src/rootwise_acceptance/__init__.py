"""Stage 0.19 acceptance evidence and release-admission workflows."""

from .evaluator import AcceptanceResult, evaluate_acceptance
from .admission import AdmissionResult, admit_release_candidate
from .recording import GateRecording, record_gate
from .workflow import ManifestInitialization, ReportInspection, initialize_manifest, inspect_report

__all__ = [
    "AcceptanceResult", "AdmissionResult", "GateRecording", "ManifestInitialization",
    "ReportInspection", "admit_release_candidate", "evaluate_acceptance",
    "initialize_manifest", "inspect_report", "record_gate",
]
