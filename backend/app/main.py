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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.grading import IMPLEMENTATIONS, PASS_MARK_THRESHOLD
from app.models import EvidenceLedger, VerificationRunReport, VerifyRequest
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
def health_check() -> dict[str, str]:
    """Return service health and phase metadata."""
    return {
        "status": "ok",
        "service": "proofloop-backend",
        "phase": "phase-1-mvp",
        "arbitrary_code_execution": "disabled",
        "external_ai_apis": "disabled",
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
