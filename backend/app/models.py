"""Pydantic data models for PROOFLOOP requirements, test checks, and evidence ledger."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class VerificationStatus(str, Enum):
    """Tri-state verification status required by PROOFLOOP MVP scope."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RequirementSpecModel(BaseModel):
    """Stated requirement linked to one or more required test IDs."""

    requirement_id: str = Field(..., description="Unique requirement identifier, e.g. REQ-01")
    title: str = Field(..., description="Concise requirement title")
    statement: str = Field(..., description="Formal requirement statement")
    required_test_ids: list[str] = Field(
        default_factory=list,
        description="IDs of test cases that must all run and pass for this requirement to be marked PASS",
    )


class TestCaseSpecModel(BaseModel):
    """Predefined, deterministic test fixture specification."""

    test_id: str = Field(..., description="Unique test case identifier, e.g. TC-01")
    requirement_id: str = Field(..., description="Requirement ID verified by this test case")
    name: str = Field(..., description="Short descriptive name of the test case")
    category: str = Field(..., description="Test category (e.g. Standard, Fault-Exposing, Boundary, Validation)")
    input_marks: list[float] = Field(..., description="Input list of subject marks")
    expected_return: Optional[bool] = Field(
        None,
        description="Expected boolean return value (True=Pass, False=Fail), or None if an exception is expected",
    )
    expected_exception: Optional[str] = Field(
        None,
        description="Expected exception class name if the input should raise an error",
    )
    expected_output_display: str = Field(
        ...,
        description="Human-readable representation of expected output",
    )
    design_note: str = Field(
        ...,
        description="Explanatory rationale for why this test case exists (kept separate from execution evidence)",
    )


class CheckEvidenceRecord(BaseModel):
    """Pure execution evidence for a single test check (kept strictly separate from explanations)."""

    requirement_id: str
    test_id: str
    test_name: str
    category: str
    implementation_id: str
    input: list[float]
    expected_output: str
    expected_return: Optional[bool] = None
    expected_exception: Optional[str] = None
    actual_output: Optional[str] = None
    actual_return: Optional[bool] = None
    exception_raised: Optional[str] = None
    executed: bool
    timed_out: bool = False
    observed_result: VerificationStatus
    execution_time_ms: Optional[float] = None


class CheckExplanationRecord(BaseModel):
    """Explanatory analysis for a test check, stored separately from raw execution evidence."""

    test_id: str
    requirement_id: str
    implementation_id: str
    input_metrics: str
    design_note: str
    diagnostic_explanation: str


class RequirementEvaluationRecord(BaseModel):
    """Aggregated verification result for a requirement based on its linked test checks."""

    requirement_id: str
    title: str
    statement: str
    required_test_ids: list[str]
    executed_test_ids: list[str]
    passed_test_ids: list[str]
    failed_test_ids: list[str]
    unknown_test_ids: list[str]
    status: VerificationStatus
    evidence_summary: str


class RunSummaryCounts(BaseModel):
    """Counts of test checks and requirements by verification status."""

    total_checks: int
    executed_checks: int
    passed_checks: int
    failed_checks: int
    unknown_checks: int
    total_requirements: int
    passed_requirements: int
    failed_requirements: int
    unknown_requirements: int


class VerificationRunReport(BaseModel):
    """Complete report for a single verification run against one predefined implementation."""

    run_id: str
    run_label: str
    timestamp: str
    implementation_id: str
    implementation_name: str
    implementation_short_label: str
    implementation_description: str
    source_code: str
    selected_test_ids: list[str]
    overall_status: VerificationStatus
    counts: RunSummaryCounts
    requirements: list[RequirementEvaluationRecord]
    evidence: list[CheckEvidenceRecord]
    explanations: list[CheckExplanationRecord]
    scope_disclaimer: str


class EvidenceLedger(BaseModel):
    """Top-level JSON evidence ledger persisted to disk and served to the frontend."""

    schema_version: str = "1.0.0"
    generated_at: str
    epistemic_principle: str
    requirements_catalog: list[RequirementSpecModel]
    test_cases_catalog: list[TestCaseSpecModel]
    runs: dict[str, VerificationRunReport]


class VerifyRequest(BaseModel):
    """Controlled request payload to run predefined tests on a predefined implementation."""

    model_config = ConfigDict(extra="forbid")

    implementation_id: str = Field(
        ...,
        description="Must match a registered predefined implementation ID ('correct_all_subjects' or 'faulty_average_only')",
    )
    selected_test_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional subset of predefined test IDs to execute. Omitted test IDs are recorded as UNKNOWN.",
    )
    run_label: Optional[str] = Field(
        default=None,
        description="Optional label for the verification run.",
    )


class GnaniConfigStatusResponse(BaseModel):
    """Safe configuration readiness status for Gnani AI Speech APIs (never exposes secret values)."""

    configured: bool
    provider: str = "Gnani AI"
    base_url: str
    stt_endpoint: str = "/stt/v3"
    tts_endpoint: str = "/api/v1/tts/inference"
    required_env_vars: list[str]
    missing_env_vars: list[str]
    default_stt_language: str = "en-IN"
    supported_stt_languages: list[str]
    supported_audio_formats: list[str]
    max_audio_bytes: int
    default_tts_model: str = "timbre-v2.5"
    default_tts_voice: str = "Kaveri"
    rate_limit_max_requests: int = 10
    rate_limit_window_seconds: int = 60
    message: str


class STTResponseModel(BaseModel):
    """Response returned after Gnani AI Prisma v2.5 Speech-to-Text transcription."""

    transcript: str
    language_code: str
    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    epistemic_notice: str = (
        "Speech transcription captures a stated request for human review only. "
        "It is not verification evidence and does not generate or execute code."
    )


class TTSRequestModel(BaseModel):
    """Controlled request to synthesize a concise verification result summary via Gnani Timbre TTS.

    Restricted strictly to stored verification run reports via run_id; arbitrary free-form
    text synthesis is not permitted.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Required Run ID in the Evidence Ledger to summarize from actual backend verification evidence.",
    )
    language: str = Field(
        default="en-IN",
        description="BCP-47 language code supported by Gnani Timbre TTS.",
    )
    voice: str = Field(
        default="Kaveri",
        description="Gnani Timbre voice name matching the selected model.",
    )
    model: str = Field(
        default="timbre-v2.5",
        description="Gnani Timbre model ('timbre-v2.5' or 'timbre-v3.0').",
    )
    speed: float = Field(
        default=1.0,
        description="Speaking speed multiplier between 0.85 and 1.15.",
    )


class TTSResponseModel(BaseModel):
    """Synthesized speech response containing the concise spoken summary and WAV audio payload."""

    summary_text: str
    audio_base64: str
    content_type: str = "audio/wav"
    run_id: str
    overall_status: VerificationStatus
    model: str
    voice: str
    language: str


