"""Deterministic unit and API tests for Gnani AI Prisma STT and Timbre TTS integration.

All upstream HTTP calls to https://api.vachana.ai are mocked via httpx.MockTransport
or monkeypatch so no real credentials, paid API calls, or network access are required.
"""

from __future__ import annotations

import base64
import io
import json
import pytest
import httpx
from fastapi.testclient import TestClient

import app.gnani_service as gnani_service
from app.gnani_service import (
    GNANI_API_KEY_ENV,
    MAX_AUDIO_UPLOAD_BYTES,
    build_spoken_summary_from_report,
    synthesize_speech_with_gnani,
    transcribe_speech_with_gnani,
)
from app.main import app
from app.models import VerificationStatus
from app.verifier import execute_verification_run

client = TestClient(app)

SAMPLE_WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


def test_voice_status_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GNANI_API_KEY_ENV, raising=False)
    response = client.get("/api/voice/status")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["provider"] == "Gnani AI"
    assert GNANI_API_KEY_ENV in data["missing_env_vars"]
    assert data["stt_endpoint"] == "/stt/v3"
    assert data["tts_endpoint"] == "/api/v1/tts/inference"


def test_voice_status_when_configured_never_leaks_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_value = "gnani_secret_test_key_999888777"
    monkeypatch.setenv(GNANI_API_KEY_ENV, secret_value)
    response = client.get("/api/voice/status")
    assert response.status_code == 200
    raw_text = response.text
    assert secret_value not in raw_text
    data = response.json()
    assert data["configured"] is True
    assert data["missing_env_vars"] == []


def test_stt_missing_credentials_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GNANI_API_KEY_ENV, raising=False)
    response = client.post(
        "/api/voice/stt",
        files={"audio_file": ("sample.wav", io.BytesIO(SAMPLE_WAV_BYTES), "audio/wav")},
        data={"language_code": "en-IN", "format": "transcribe"},
    )
    assert response.status_code == 503
    assert "GNANI_API_KEY" in response.json()["detail"]


def test_stt_rejects_empty_and_oversized_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "dummy_key_for_validation")

    # 1. Empty upload (0 bytes)
    empty_resp = client.post(
        "/api/voice/stt",
        files={"audio_file": ("empty.wav", io.BytesIO(b""), "audio/wav")},
        data={"language_code": "en-IN"},
    )
    assert empty_resp.status_code == 400
    assert "empty" in empty_resp.json()["detail"].lower()

    # 2. Oversized upload (> 5 MB)
    oversized_bytes = b"a" * (MAX_AUDIO_UPLOAD_BYTES + 10)
    large_resp = client.post(
        "/api/voice/stt",
        files={"audio_file": ("huge.wav", io.BytesIO(oversized_bytes), "audio/wav")},
        data={"language_code": "en-IN"},
    )
    assert large_resp.status_code == 413
    assert "exceeds" in large_resp.json()["detail"].lower()


def test_stt_rejects_unsupported_audio_types_and_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "dummy_key_for_validation")

    # Unsupported media type / extension
    bad_type = client.post(
        "/api/voice/stt",
        files={"audio_file": ("script.py", io.BytesIO(b"print(1)"), "text/x-python")},
        data={"language_code": "en-IN"},
    )
    assert bad_type.status_code == 415

    # Unsupported language code
    bad_lang = client.post(
        "/api/voice/stt",
        files={"audio_file": ("sample.wav", io.BytesIO(SAMPLE_WAV_BYTES), "audio/wav")},
        data={"language_code": "fr-FR"},
    )
    assert bad_lang.status_code == 400


def test_stt_success_with_mocked_gnani_rest_api(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_key = "test_secret_gnani_key_stt"
    monkeypatch.setenv(GNANI_API_KEY_ENV, secret_key)

    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert request.url == httpx.URL("https://api.vachana.ai/stt/v3")
        assert request.headers.get("X-API-Key-ID") == secret_key
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req_gnani_001",
                "timestamp": "20261019_120000.000",
                "transcript": "Verify that a student passes only when every mark is at least 40.",
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    result = transcribe_speech_with_gnani(
        audio_bytes=SAMPLE_WAV_BYTES,
        filename="requirement.wav",
        content_type="audio/wav",
        language_code="en-IN",
        stt_format="transcribe",
        http_client=mock_client,
    )

    assert len(captured_requests) == 1
    assert result.transcript == "Verify that a student passes only when every mark is at least 40."
    assert result.request_id == "req_gnani_001"
    assert result.language_code == "en-IN"
    assert "not verification evidence" in result.epistemic_notice


@pytest.mark.parametrize(
    ("upstream_status", "upstream_body", "expected_status"),
    [
        (
            401,
            {"success": False, "error": {"type": "FORBIDDEN", "message": "Invalid key secret_val"}},
            502,
        ),
        (
            403,
            {"success": False, "error": {"type": "FORBIDDEN", "message": "No permission"}},
            502,
        ),
        (
            429,
            {"success": False, "error": {"type": "RATE_LIMIT_ERROR", "message": "Rate limit exceeded"}},
            429,
        ),
        (
            503,
            {"success": False, "error": {"type": "SERVICE_UNAVAILABLE", "message": "Service down"}},
            503,
        ),
    ],
)
def test_stt_upstream_error_handling_and_secret_redaction(
    monkeypatch: pytest.MonkeyPatch,
    upstream_status: int,
    upstream_body: dict[str, object],
    expected_status: int,
) -> None:
    secret_key = "secret_val"
    monkeypatch.setenv(GNANI_API_KEY_ENV, secret_key)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(upstream_status, json=upstream_body)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(gnani_service.GnaniUpstreamError) as exc_info:
        transcribe_speech_with_gnani(
            audio_bytes=SAMPLE_WAV_BYTES,
            filename="sample.wav",
            content_type="audio/wav",
            http_client=mock_client,
        )

    assert exc_info.value.status_code == expected_status
    assert secret_key not in exc_info.value.message


def test_stt_timeout_and_malformed_response_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "test_key_timeout")

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Upstream read timed out", request=request)

    timeout_client = httpx.Client(transport=httpx.MockTransport(timeout_handler))
    with pytest.raises(gnani_service.GnaniUpstreamError) as timeout_exc:
        transcribe_speech_with_gnani(
            audio_bytes=SAMPLE_WAV_BYTES,
            http_client=timeout_client,
        )
    assert timeout_exc.value.status_code == 504

    def malformed_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-valid-json", headers={"content-type": "text/plain"})

    malformed_client = httpx.Client(transport=httpx.MockTransport(malformed_handler))
    with pytest.raises(gnani_service.GnaniUpstreamError) as malformed_exc:
        transcribe_speech_with_gnani(
            audio_bytes=SAMPLE_WAV_BYTES,
            http_client=malformed_client,
        )
    assert malformed_exc.value.status_code == 502


def test_tts_success_and_spoken_summary_preserves_verification_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_key = "test_secret_gnani_key_tts"
    monkeypatch.setenv(GNANI_API_KEY_ENV, secret_key)

    faulty_report = execute_verification_run(implementation_id="faulty_average_only")
    assert faulty_report.overall_status == VerificationStatus.FAIL

    summary_text = build_spoken_summary_from_report(faulty_report)
    assert "FAIL" in summary_text
    assert "TC-02" in summary_text
    assert faulty_report.implementation_name in summary_text

    def tts_handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.vachana.ai/api/v1/tts/inference")
        assert request.headers.get("X-API-Key-ID") == secret_key
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "timbre-v2.5"
        assert body["voice"] == "Kaveri"
        assert body["language"] == "en-IN"
        assert body["audio_config"]["container"] == "wav"
        return httpx.Response(
            200,
            content=SAMPLE_WAV_BYTES,
            headers={"content-type": "audio/wav"},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(tts_handler))
    tts_result = synthesize_speech_with_gnani(
        summary_text=summary_text,
        model="timbre-v2.5",
        voice="Kaveri",
        language="en-IN",
        speed=1.0,
        run_id="faulty_full",
        overall_status=faulty_report.overall_status,
        http_client=mock_client,
    )

    # Underlying verification status must remain FAIL even when TTS succeeds
    assert tts_result.overall_status == VerificationStatus.FAIL
    assert tts_result.content_type == "audio/wav"
    assert base64.b64decode(tts_result.audio_base64) == SAMPLE_WAV_BYTES


def test_tts_endpoint_handles_missing_credentials_and_invalid_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(GNANI_API_KEY_ENV, raising=False)

    # Missing credentials on valid run_id
    resp_unconfigured = client.post("/api/voice/tts", json={"run_id": "faulty_full"})
    assert resp_unconfigured.status_code == 503
    assert "GNANI_API_KEY" in resp_unconfigured.json()["detail"]

    # Unknown run_id returns 404
    resp_not_found = client.post("/api/voice/tts", json={"run_id": "nonexistent_run"})
    assert resp_not_found.status_code == 404

    # Unsupported voice for timbre-v2.5 returns 400
    monkeypatch.setenv(GNANI_API_KEY_ENV, "dummy_key")
    resp_bad_voice = client.post(
        "/api/voice/tts",
        json={"run_id": "correct_full", "model": "timbre-v2.5", "voice": "NonExistentVoice"},
    )
    assert resp_bad_voice.status_code == 400
