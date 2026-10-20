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
    GNANI_RATE_LIMIT_MAX_REQUESTS_ENV,
    GNANI_RATE_LIMIT_WINDOW_SECONDS_ENV,
    MAX_AUDIO_UPLOAD_BYTES,
    MAX_TTS_AUDIO_RESPONSE_BYTES,
    build_spoken_summary_from_report,
    synthesize_speech_with_gnani,
    transcribe_speech_with_gnani,
    voice_rate_limiter,
)
from app.main import app
from app.models import VerificationStatus
from app.verifier import execute_verification_run

client = TestClient(app)

SAMPLE_WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    voice_rate_limiter.reset()



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


def test_tts_rejects_arbitrary_free_form_text_and_unknown_run_id_without_calling_gnani(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "dummy_key")
    gnani_called = False

    def _forbidden_gnani_call(*_args: object, **_kwargs: object) -> object:
        nonlocal gnani_called
        gnani_called = True
        raise AssertionError("Gnani TTS should not be called when request validation or run lookup fails")

    monkeypatch.setattr("app.main.synthesize_speech_with_gnani", _forbidden_gnani_call)

    # 1. Free-form text without run_id is rejected (422)
    resp_free_text = client.post("/api/voice/tts", json={"text": "Synthesize arbitrary user text"})
    assert resp_free_text.status_code == 422

    # 2. Extra text field alongside run_id is rejected (extra="forbid" -> 422)
    resp_extra_text = client.post(
        "/api/voice/tts",
        json={"run_id": "correct_full", "text": "Override summary"},
    )
    assert resp_extra_text.status_code == 422

    # 3. Unknown run_id is rejected with 404 before calling Gnani
    resp_unknown = client.post("/api/voice/tts", json={"run_id": "unknown_run_999"})
    assert resp_unknown.status_code == 404
    assert gnani_called is False


def test_tts_preserves_pass_fail_and_unknown_statuses_from_stored_reports() -> None:
    correct_report = execute_verification_run(implementation_id="correct_all_subjects")
    faulty_report = execute_verification_run(implementation_id="faulty_average_only")
    unknown_report = execute_verification_run(
        implementation_id="faulty_average_only",
        selected_test_ids=["TC-01", "TC-03"],
    )

    assert correct_report.overall_status == VerificationStatus.PASS
    assert faulty_report.overall_status == VerificationStatus.FAIL
    assert unknown_report.overall_status == VerificationStatus.UNKNOWN

    assert "overall status is PASS" in build_spoken_summary_from_report(correct_report)
    assert "overall status is FAIL" in build_spoken_summary_from_report(faulty_report)
    assert "overall status is UNKNOWN" in build_spoken_summary_from_report(unknown_report)


@pytest.mark.parametrize(
    ("content_type", "body_bytes", "expected_error_code"),
    [
        (
            "text/html; charset=utf-8",
            b"<html><body>502 Bad Gateway</body></html>" + b" " * 40,
            "GNANI_TTS_INVALID_CONTENT_TYPE",
        ),
        (
            "application/json",
            b'{"error": "unexpected json body"}' + b" " * 40,
            "GNANI_TTS_INVALID_CONTENT_TYPE",
        ),
        (
            "audio/wav",
            b"",
            "GNANI_TTS_MALFORMED_AUDIO",
        ),
        (
            "audio/wav",
            b"RIFF\x10\x00\x00\x00WAVEshort",
            "GNANI_TTS_MALFORMED_AUDIO",
        ),
        (
            "audio/wav",
            b"NOT_A_RIFF_WAVE_HEADER_AT_ALL_BUT_AT_LEAST_44_BYTES_LONG_PAYLOAD",
            "GNANI_TTS_MALFORMED_AUDIO",
        ),
    ],
)
def test_tts_rejects_invalid_content_type_and_malformed_or_non_wav_audio(
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    body_bytes: bytes,
    expected_error_code: str,
) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "test_key_wav_validation")

    def bad_audio_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body_bytes,
            headers={"content-type": content_type},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(bad_audio_handler))
    with pytest.raises(gnani_service.GnaniUpstreamError) as exc_info:
        synthesize_speech_with_gnani(
            summary_text="PROOFLOOP verification result: overall status is PASS.",
            run_id="correct_full",
            overall_status=VerificationStatus.PASS,
            http_client=mock_client,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == expected_error_code


def test_voice_endpoints_enforce_rate_limit_before_calling_gnani(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GNANI_RATE_LIMIT_MAX_REQUESTS_ENV, "2")
    monkeypatch.setenv(GNANI_RATE_LIMIT_WINDOW_SECONDS_ENV, "60")
    monkeypatch.delenv(GNANI_API_KEY_ENV, raising=False)

    # First two requests pass the rate limiter (and hit the 503 missing-key check)
    r1 = client.post("/api/voice/tts", json={"run_id": "correct_full"})
    r2 = client.post("/api/voice/tts", json={"run_id": "correct_full"})
    assert r1.status_code == 503
    assert r2.status_code == 503

    # Third request within the window is blocked by the rate limiter with 429
    r3 = client.post("/api/voice/tts", json={"run_id": "correct_full"})
    assert r3.status_code == 429
    assert "rate limit exceeded" in r3.json()["detail"].lower()

    # STT endpoint shares the voice rate limiter and is also blocked with 429
    r4 = client.post(
        "/api/voice/stt",
        files={"audio_file": ("sample.wav", io.BytesIO(SAMPLE_WAV_BYTES), "audio/wav")},
        data={"language_code": "en-IN"},
    )
    assert r4.status_code == 429


class _TrackingByteStream(httpx.SyncByteStream):
    """Test helper stream that tracks how many chunks were consumed and whether close() was called."""

    def __init__(self, chunks: list[bytes], *, raise_after_first_chunk: Exception | None = None) -> None:
        self._chunks = chunks
        self._raise_after_first_chunk = raise_after_first_chunk
        self.chunks_yielded = 0
        self.bytes_yielded = 0
        self.closed = False

    def __iter__(self):
        for idx, chunk in enumerate(self._chunks):
            if idx == 1 and self._raise_after_first_chunk is not None:
                raise self._raise_after_first_chunk
            self.chunks_yielded += 1
            self.bytes_yielded += len(chunk)
            yield chunk

    def close(self) -> None:
        self.closed = True


class _LazyOversizedWavStream(httpx.SyncByteStream):
    """Lazily generates 1 MB WAV chunks to verify streaming stops as soon as MAX_TTS_AUDIO_RESPONSE_BYTES is exceeded."""

    def __init__(self, chunk_size: int, total_chunks: int) -> None:
        self.chunk_size = chunk_size
        self.total_chunks = total_chunks
        self.chunks_yielded = 0
        self.bytes_yielded = 0
        self.closed = False

    def __iter__(self):
        for idx in range(self.total_chunks):
            self.chunks_yielded += 1
            if idx == 0:
                chunk = SAMPLE_WAV_BYTES + (b"\x00" * (self.chunk_size - len(SAMPLE_WAV_BYTES)))
            else:
                chunk = b"\x00" * self.chunk_size
            self.bytes_yielded += len(chunk)
            yield chunk

    def close(self) -> None:
        self.closed = True


def test_tts_oversized_stream_stops_early_without_buffering_entire_response_and_closes_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "test_key_oversized_stream")

    one_mb = 1024 * 1024
    # 25 MB total across 25 chunks; limit is 10 MB (10 chunks)
    oversized_stream = _LazyOversizedWavStream(chunk_size=one_mb, total_chunks=25)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "audio/wav"},
            stream=oversized_stream,
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(gnani_service.GnaniUpstreamError) as exc_info:
        synthesize_speech_with_gnani(
            summary_text="PROOFLOOP verification result: overall status is PASS.",
            run_id="correct_full",
            overall_status=VerificationStatus.PASS,
            http_client=mock_client,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "GNANI_TTS_OVERSIZED_AUDIO"
    # Only 11 chunks (10 MB buffered + the 11th chunk that triggered the cap) were ever pulled;
    # the remaining 14 MB (chunks 12..25) were never read from the stream.
    assert oversized_stream.chunks_yielded == 11
    assert oversized_stream.bytes_yielded == MAX_TTS_AUDIO_RESPONSE_BYTES + one_mb
    assert oversized_stream.closed is True


def test_tts_valid_multi_chunk_stream_succeeds_and_closes_response_on_all_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GNANI_API_KEY_ENV, "test_key_streaming_paths")

    # 1. Valid multi-chunk WAV stream succeeds and closes stream
    valid_chunks = [SAMPLE_WAV_BYTES[:16], SAMPLE_WAV_BYTES[16:32], SAMPLE_WAV_BYTES[32:]]
    valid_stream = _TrackingByteStream(valid_chunks)

    mock_valid_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(200, headers={"content-type": "audio/wav"}, stream=valid_stream)
        )
    )
    result = synthesize_speech_with_gnani(
        summary_text="PROOFLOOP verification result: overall status is PASS.",
        run_id="correct_full",
        overall_status=VerificationStatus.PASS,
        http_client=mock_valid_client,
    )
    assert base64.b64decode(result.audio_base64) == SAMPLE_WAV_BYTES
    assert valid_stream.chunks_yielded == 3
    assert valid_stream.closed is True

    # 2. Invalid Content-Type rejects before reading body chunks and closes stream
    wrong_ct_stream = _TrackingByteStream([b"<html>error</html>"])
    mock_wrong_ct_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(200, headers={"content-type": "text/html"}, stream=wrong_ct_stream)
        )
    )
    with pytest.raises(gnani_service.GnaniUpstreamError) as ct_exc:
        synthesize_speech_with_gnani(
            summary_text="PROOFLOOP verification result: overall status is PASS.",
            run_id="correct_full",
            overall_status=VerificationStatus.PASS,
            http_client=mock_wrong_ct_client,
        )
    assert ct_exc.value.error_code == "GNANI_TTS_INVALID_CONTENT_TYPE"
    assert wrong_ct_stream.chunks_yielded == 0
    assert wrong_ct_stream.closed is True

    # 3. Upstream HTTP error (e.g. 503) maps error and closes stream
    error_stream = _TrackingByteStream([b'{"success": false, "error": {"message": "Temporarily unavailable"}}'])
    mock_error_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(503, headers={"content-type": "application/json"}, stream=error_stream)
        )
    )
    with pytest.raises(gnani_service.GnaniUpstreamError) as upstream_exc:
        synthesize_speech_with_gnani(
            summary_text="PROOFLOOP verification result: overall status is PASS.",
            run_id="correct_full",
            overall_status=VerificationStatus.PASS,
            http_client=mock_error_client,
        )
    assert upstream_exc.value.status_code == 503
    assert upstream_exc.value.error_code == "GNANI_SERVICE_UNAVAILABLE"
    assert error_stream.closed is True

    # 4. Mid-stream timeout maps to 504 GNANI_TTS_TIMEOUT and closes stream
    def timeout_stream_handler(request: httpx.Request) -> httpx.Response:
        stream = _TrackingByteStream(
            [SAMPLE_WAV_BYTES[:20], SAMPLE_WAV_BYTES[20:]],
            raise_after_first_chunk=httpx.ReadTimeout("Mid-stream timeout", request=request),
        )
        timeout_stream_handler.last_stream = stream  # type: ignore[attr-defined]
        return httpx.Response(200, headers={"content-type": "audio/wav"}, stream=stream)

    mock_timeout_client = httpx.Client(transport=httpx.MockTransport(timeout_stream_handler))
    with pytest.raises(gnani_service.GnaniUpstreamError) as timeout_exc:
        synthesize_speech_with_gnani(
            summary_text="PROOFLOOP verification result: overall status is PASS.",
            run_id="correct_full",
            overall_status=VerificationStatus.PASS,
            http_client=mock_timeout_client,
        )
    assert timeout_exc.value.status_code == 504
    assert timeout_exc.value.error_code == "GNANI_TTS_TIMEOUT"
    assert timeout_stream_handler.last_stream.closed is True  # type: ignore[attr-defined]


