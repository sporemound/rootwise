"""Stage 0.20 acceptance, admission, and admission-verification workflows."""

from .evaluator import AcceptanceResult, evaluate_acceptance
from .admission import AdmissionResult, admit_release_candidate
from .admission_verification import AdmissionVerification, verify_admission
from .recording import GateRecording, record_gate
from .workflow import ManifestInitialization, ReportInspection, initialize_manifest, inspect_report

__all__ = [
    "AcceptanceResult", "AdmissionResult", "AdmissionVerification", "GateRecording",
    "ManifestInitialization", "ReportInspection", "admit_release_candidate",
    "evaluate_acceptance", "initialize_manifest", "inspect_report", "record_gate",
    "verify_admission",
]
