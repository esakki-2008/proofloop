"""FastAPI backend for PROOFLOOP Phase 1 MVP.

Provides deterministic execution of predefined verification checks against fixed
student-grading implementations and serves the JSON Evidence Ledger.

Security policy:
- No arbitrary code execution or shell access is exposed.
- No external AI APIs are called in Phase 1.
- No secrets are hardcoded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.gnani_service import (
    MAX_AUDIO_UPLOAD_BYTES,
    GnaniServiceError,
    build_spoken_summary_from_report,
    get_gnani_config_status,
    synthesize_speech_with_gnani,
    transcribe_speech_with_gnani,
    voice_rate_limiter,
)
from app.grading import IMPLEMENTATIONS, PASS_MARK_THRESHOLD
from app.models import (
    EvidenceLedger,
    GnaniConfigStatusResponse,
    STTResponseModel,
    TTSRequestModel,
    TTSResponseModel,
    VerificationRunReport,
    VerifyRequest,
)
from app.verifier import (
    EPISTEMIC_PRINCIPLE,
    REQUIREMENTS_CATALOG,
    TEST_CASES_CATALOG,
    build_default_ledger,
    execute_verification_run,
    load_or_create_ledger,
    save_ledger,
)

app = FastAPI(
    title="PROOFLOOP Verification Engine API",
    description=(
        "Evidence-based Python verification prototype (Phase 1 MVP). "
        "Connects stated requirements to executable checks and records factual evidence."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, object]:
    """Return service health, phase metadata, and accurate capability boundaries."""
    gnani_status = get_gnani_config_status()
    return {
        "status": "ok",
        "service": "proofloop-backend",
        "phase": "phase-2-gnani-voice",
        "arbitrary_code_execution": "disabled",
        "verification_engine": "deterministic-local-only",
        "external_ai_apis": "gnani-speech-only",
        "gnani_voice_configured": gnani_status.configured,
    }


@app.get("/api/catalog")
def get_catalog() -> dict[str, object]:
    """Return the fixed catalog of implementations, requirements, and test cases."""
    implementations_list = [
        {
            "implementation_id": spec.implementation_id,
            "name": spec.name,
            "short_label": spec.short_label,
            "description": spec.description,
            "is_reference_correct": spec.is_reference_correct,
            "source_code": spec.source_code,
        }
        for spec in IMPLEMENTATIONS.values()
    ]
    return {
        "pass_mark_threshold": PASS_MARK_THRESHOLD,
        "epistemic_principle": EPISTEMIC_PRINCIPLE,
        "implementations": implementations_list,
        "requirements": [req.model_dump(mode="json") for req in REQUIREMENTS_CATALOG],
        "test_cases": [tc.model_dump(mode="json") for tc in TEST_CASES_CATALOG],
    }


@app.get("/api/ledger", response_model=EvidenceLedger)
def get_evidence_ledger() -> EvidenceLedger:
    """Return the persisted JSON Evidence Ledger (generating baseline runs if absent)."""
    return load_or_create_ledger()


@app.post("/api/ledger/reset", response_model=EvidenceLedger)
def reset_evidence_ledger() -> EvidenceLedger:
    """Re-execute all baseline verification scenarios deterministically and persist to JSON."""
    return build_default_ledger(persist=True)


@app.post("/api/verify", response_model=VerificationRunReport)
def run_verification(request: VerifyRequest) -> VerificationRunReport:
    """Execute a controlled verification run on a predefined implementation and test subset."""
    try:
        report = execute_verification_run(
            implementation_id=request.implementation_id,
            selected_test_ids=request.selected_test_ids,
            run_id="custom_run",
            run_label=request.run_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ledger = load_or_create_ledger()
    ledger.generated_at = datetime.now(timezone.utc).isoformat()
    ledger.runs["custom_run"] = report
    save_ledger(ledger)
    return report


@app.get("/api/voice/status", response_model=GnaniConfigStatusResponse)
def get_voice_status() -> GnaniConfigStatusResponse:
    """Return safe configuration status for Gnani AI Speech-to-Text and Text-to-Speech."""
    return get_gnani_config_status()


def _resolve_client_id(http_request: Request) -> str:
    """Resolve client identifier for per-client in-memory rate limiting."""
    if http_request.client and http_request.client.host:
        return http_request.client.host
    return "anonymous"


@app.post("/api/voice/stt", response_model=STTResponseModel)
async def transcribe_voice(
    http_request: Request,
    audio_file: UploadFile = File(...),
    language_code: str = Form("en-IN"),
    format: str = Form("transcribe"),
) -> STTResponseModel:
    """Transcribe an uploaded audio clip using Gnani AI Prisma v2.5 Speech-to-Text."""
    try:
        voice_rate_limiter.check_and_record(_resolve_client_id(http_request))
    except GnaniServiceError as exc:
        await audio_file.close()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    try:
        audio_bytes = await audio_file.read(MAX_AUDIO_UPLOAD_BYTES + 1)
    finally:
        await audio_file.close()

    try:
        return transcribe_speech_with_gnani(
            audio_bytes=audio_bytes,
            filename=audio_file.filename,
            content_type=audio_file.content_type,
            language_code=language_code,
            stt_format=format,
        )
    except GnaniServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.post("/api/voice/tts", response_model=TTSResponseModel)
def synthesize_voice_summary(
    request: TTSRequestModel,
    http_request: Request,
) -> TTSResponseModel:
    """Synthesize a concise spoken summary derived from a stored VerificationRunReport."""
    try:
        voice_rate_limiter.check_and_record(_resolve_client_id(http_request))
    except GnaniServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    ledger = load_or_create_ledger()
    run_report = ledger.runs.get(request.run_id)
    if run_report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Verification run '{request.run_id}' not found in the Evidence Ledger.",
        )

    summary_text = build_spoken_summary_from_report(run_report)
    overall_status = run_report.overall_status

    try:
        return synthesize_speech_with_gnani(
            summary_text=summary_text,
            run_id=request.run_id,
            overall_status=overall_status,
            model=request.model,
            voice=request.voice,
            language=request.language,
            speed=request.speed,
        )
    except GnaniServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


