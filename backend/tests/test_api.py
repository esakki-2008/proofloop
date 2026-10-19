"""API endpoint and security constraint tests for PROOFLOOP FastAPI backend."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["phase"] == "phase-2-gnani-voice"
    assert payload["arbitrary_code_execution"] == "disabled"
    assert payload["verification_engine"] == "deterministic-local-only"
    assert payload["external_ai_apis"] == "gnani-speech-only"
    assert isinstance(payload["gnani_voice_configured"], bool)



def test_catalog_endpoint_returns_fixed_implementations_and_tests() -> None:
    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pass_mark_threshold"] == 40
    impl_ids = [item["implementation_id"] for item in payload["implementations"]]
    assert impl_ids == ["correct_all_subjects", "faulty_average_only"]
    assert len(payload["requirements"]) == 3
    assert len(payload["test_cases"]) == 8


def test_ledger_endpoint_includes_pass_fail_and_unknown_runs() -> None:
    response = client.post("/api/ledger/reset")
    assert response.status_code == 200
    ledger = response.json()
    runs = ledger["runs"]
    assert runs["correct_full"]["overall_status"] == "PASS"
    assert runs["faulty_full"]["overall_status"] == "FAIL"
    assert runs["incomplete_coverage_demo"]["overall_status"] == "UNKNOWN"


def test_verify_endpoint_executes_controlled_runs_and_rejects_arbitrary_code() -> None:
    # 1. Valid controlled run
    resp = client.post(
        "/api/verify",
        json={
            "implementation_id": "faulty_average_only",
            "selected_test_ids": ["TC-01", "TC-02"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_status"] == "FAIL"
    assert data["counts"]["executed_checks"] == 2
    assert data["counts"]["unknown_checks"] == 6

    # 2. Reject unknown implementation_id
    bad_impl = client.post(
        "/api/verify",
        json={"implementation_id": "arbitrary_user_function"},
    )
    assert bad_impl.status_code == 400

    # 3. Reject unknown test_id
    bad_test = client.post(
        "/api/verify",
        json={
            "implementation_id": "correct_all_subjects",
            "selected_test_ids": ["TC-999"],
        },
    )
    assert bad_test.status_code == 400

    # 4. Reject arbitrary code injection fields (extra="forbid")
    code_injection = client.post(
        "/api/verify",
        json={
            "implementation_id": "correct_all_subjects",
            "code": "import os; os.system('whoami')",
        },
    )
    assert code_injection.status_code == 422

    # Restore clean baseline ledger after test
    reset_resp = client.post("/api/ledger/reset")
    assert reset_resp.status_code == 200

