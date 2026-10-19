"""Gnani AI Speech-to-Text (Prisma v2.5) and Text-to-Speech (Timbre v2.5/v3.0) integration.

Official documentation references:
- Base URL & Auth: https://docs.gnani.ai/api/introduction/introduction
  - Base URL: https://api.vachana.ai
  - Header: X-API-Key-ID: <GNANI_API_KEY>
- STT REST: https://docs.gnani.ai/api/STT/speech-to-text
  - Endpoint: POST https://api.vachana.ai/stt/v3 (multipart/form-data)
- TTS REST: https://docs.gnani.ai/api/TTS/tts-inference
  - Endpoint: POST https://api.vachana.ai/api/v1/tts/inference (application/json)
- Official Python SDK reference: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana

Security & Epistemic Policy:
- Credentials are read exclusively from server-side environment variables (GNANI_API_KEY)
  and are never exposed in responses, errors, or logs.
- Uploaded audio and transcripts are processed in-memory only and never persisted to disk.
- Voice is an interface layer only and never alters verification status or executes code.
"""

from __future__ import annotations

import base64
from collections import deque
import os
from pathlib import Path
import threading
import time
from typing import Optional

import httpx

from app.models import (
    GnaniConfigStatusResponse,
    STTResponseModel,
    TTSResponseModel,
    VerificationRunReport,
    VerificationStatus,
)

GNANI_API_KEY_ENV: str = "GNANI_API_KEY"
GNANI_BASE_URL_ENV: str = "GNANI_BASE_URL"
GNANI_TIMEOUT_ENV: str = "GNANI_TIMEOUT_SECONDS"
GNANI_RATE_LIMIT_MAX_REQUESTS_ENV: str = "GNANI_RATE_LIMIT_MAX_REQUESTS"
GNANI_RATE_LIMIT_WINDOW_SECONDS_ENV: str = "GNANI_RATE_LIMIT_WINDOW_SECONDS"

DEFAULT_GNANI_BASE_URL: str = "https://api.vachana.ai"
GNANI_STT_ENDPOINT: str = "/stt/v3"
GNANI_TTS_ENDPOINT: str = "/api/v1/tts/inference"
GNANI_AUTH_HEADER: str = "X-API-Key-ID"

DEFAULT_TIMEOUT_SECONDS: float = 15.0
MIN_TIMEOUT_SECONDS: float = 1.0
MAX_TIMEOUT_SECONDS: float = 60.0

DEFAULT_RATE_LIMIT_MAX_REQUESTS: int = 10
DEFAULT_RATE_LIMIT_WINDOW_SECONDS: int = 60
MAX_TRACKED_RATE_LIMIT_CLIENTS: int = 1024

MAX_AUDIO_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MB limit for short voice clips
MAX_TTS_AUDIO_RESPONSE_BYTES: int = 10 * 1024 * 1024  # 10 MB upper bound for synthesized WAV summary
MIN_WAV_HEADER_BYTES: int = 44
MAX_TTS_TEXT_LENGTH: int = 600

ACCEPTED_TTS_WAV_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/vnd.wave",
    }
)

SUPPORTED_STT_LANGUAGES: tuple[str, ...] = (
    "en-IN",
    "hi-IN",
    "ta-IN",
    "te-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "bn-IN",
    "gu-IN",
    "pa-IN",
)

SUPPORTED_TTS_LANGUAGES: frozenset[str] = frozenset(
    {
        "auto",
        "en-IN",
        "hi-IN",
        "hi-en",
        "ta-IN",
        "te-IN",
        "kn-IN",
        "ml-IN",
        "mr-IN",
        "bn-IN",
        "gu-IN",
        "pa-IN",
    }
)

SUPPORTED_AUDIO_EXTENSIONS: tuple[str, ...] = (
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
    ".aac",
    ".m4a",
)

SUPPORTED_AUDIO_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/vnd.wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "application/ogg",
        "audio/flac",
        "audio/x-flac",
        "audio/aac",
        "audio/mp4",
        "audio/x-m4a",
        "audio/m4a",
    }
)

TIMBRE_V25_VOICES: frozenset[str] = frozenset(
    {
        "Nalini",
        "Bhavna",
        "Yashvi",
        "Urmila",
        "Jwala",
        "Chitra",
        "Ambuja",
        "Deepak",
        "Roopesh",
        "Vikrant",
        "Hemraj",
        "Jalaj",
        "Omkar",
        "Kaveri",
        "Trupti",
        "Devika",
        "Pranav",
        "Shlok",
        "Girish",
        "Asmita",
        "Trisha",
        "Brinda",
        "Vedika",
        "Noopur",
        "Suhana",
        "Lehara",
        "Lavanya",
        "Yukti",
        "Varuni",
        "Saanvi",
        "Kavin",
        "Reshma",
        "Riyaan",
        "Zahira",
        "Ishaan",
        "Kirra",
        "Dhruva",
        "Falak",
        "Veera",
        "Mehuli",
        "Zayan",
        "Poorvi",
    }
)

TIMBRE_V30_VOICES: frozenset[str] = frozenset(
    {
        "Avinash",
        "Shivani",
        "Lakshmi",
        "Kalpana",
        "Shubham",
        "Prakash",
        "Devansh",
        "Yashraj",
        "Chetana",
        "Vasudha",
        "Riyaa",
        "Tarika",
        "Harshad",
    }
)

SUPPORTED_TTS_MODELS: dict[str, frozenset[str]] = {
    "timbre-v2.5": TIMBRE_V25_VOICES,
    "timbre-v3.0": TIMBRE_V30_VOICES,
}


class GnaniServiceError(Exception):
    """Base exception for safe, user-reportable Gnani service errors."""

    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


class GnaniConfigurationError(GnaniServiceError):
    """Raised when required Gnani server credentials are not configured."""

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(
            status_code=503,
            error_code="GNANI_NOT_CONFIGURED",
            message=message
            or (
                f"Gnani AI voice integration is not configured on the server. "
                f"Set the {GNANI_API_KEY_ENV} environment variable on the backend."
            ),
        )


class GnaniValidationError(GnaniServiceError):
    """Raised when client-supplied audio or TTS parameters fail validation."""


class GnaniUpstreamError(GnaniServiceError):
    """Raised when the upstream Gnani API returns an error, times out, or is unreachable."""


class GnaniRateLimitExceededError(GnaniServiceError):
    """Raised when a client exceeds the local sliding-window voice endpoint rate limit."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        super().__init__(
            status_code=429,
            error_code="VOICE_RATE_LIMIT_EXCEEDED",
            message=(
                f"Voice request rate limit exceeded (maximum {max_requests} requests "
                f"per {window_seconds} seconds). Please wait before retrying."
            ),
        )


def _get_rate_limit_config() -> tuple[int, int]:
    raw_max = os.environ.get(GNANI_RATE_LIMIT_MAX_REQUESTS_ENV, "").strip()
    raw_window = os.environ.get(GNANI_RATE_LIMIT_WINDOW_SECONDS_ENV, "").strip()
    try:
        max_reqs = max(1, min(1000, int(raw_max))) if raw_max else DEFAULT_RATE_LIMIT_MAX_REQUESTS
    except ValueError:
        max_reqs = DEFAULT_RATE_LIMIT_MAX_REQUESTS
    try:
        window_secs = (
            max(1, min(3600, int(raw_window))) if raw_window else DEFAULT_RATE_LIMIT_WINDOW_SECONDS
        )
    except ValueError:
        window_secs = DEFAULT_RATE_LIMIT_WINDOW_SECONDS
    return max_reqs, window_secs


class VoiceRateLimiter:
    """In-memory sliding-window rate limiter to protect Gnani voice endpoints from public abuse.

    Note on multi-worker deployments:
        State is stored per Python worker process in memory and resets on process restart.
        For multi-worker or public production deployments, pair this with a shared store
        (e.g. Redis) or an upstream reverse-proxy rate limiter.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests_by_client: dict[str, deque[float]] = {}

    def check_and_record(self, client_id: str) -> None:
        max_requests, window_seconds = _get_rate_limit_config()
        now = time.monotonic()
        cutoff = now - float(window_seconds)
        normalized_client = (client_id or "anonymous").strip() or "anonymous"

        with self._lock:
            if (
                normalized_client not in self._requests_by_client
                and len(self._requests_by_client) >= MAX_TRACKED_RATE_LIMIT_CLIENTS
            ):
                # Evict expired entries first; if still full, evict oldest tracked client key
                expired_keys = [
                    k
                    for k, timestamps in self._requests_by_client.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for k in expired_keys:
                    del self._requests_by_client[k]
                if len(self._requests_by_client) >= MAX_TRACKED_RATE_LIMIT_CLIENTS:
                    oldest_key = next(iter(self._requests_by_client))
                    del self._requests_by_client[oldest_key]

            bucket = self._requests_by_client.setdefault(normalized_client, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= max_requests:
                raise GnaniRateLimitExceededError(
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                )

            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._requests_by_client.clear()


voice_rate_limiter = VoiceRateLimiter()



def _get_api_key() -> str:
    return os.environ.get(GNANI_API_KEY_ENV, "").strip()


def _get_base_url() -> str:
    raw = os.environ.get(GNANI_BASE_URL_ENV, DEFAULT_GNANI_BASE_URL).strip()
    return (raw or DEFAULT_GNANI_BASE_URL).rstrip("/")


def _get_timeout_seconds() -> float:
    raw = os.environ.get(GNANI_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        val = float(raw)
        return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, val))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _redact_secret(text: str, secret: str) -> str:
    """Ensure the API key never appears in any error string."""
    if not secret or not text:
        return text
    return text.replace(secret, "[REDACTED]")


def get_gnani_config_status() -> GnaniConfigStatusResponse:
    """Inspect server environment variables and return a safe configuration summary."""
    api_key = _get_api_key()
    configured = bool(api_key)
    missing = [] if configured else [GNANI_API_KEY_ENV]
    max_requests, window_seconds = _get_rate_limit_config()
    message = (
        "Gnani AI Prisma STT and Timbre TTS are configured."
        if configured
        else (
            f"Gnani AI credentials are not configured ({GNANI_API_KEY_ENV} is unset). "
            "Voice transcription and speech synthesis are disabled until configured; "
            "all deterministic verification and Evidence Ledger controls remain active."
        )
    )
    return GnaniConfigStatusResponse(
        configured=configured,
        provider="Gnani AI",
        base_url=_get_base_url(),
        stt_endpoint=GNANI_STT_ENDPOINT,
        tts_endpoint=GNANI_TTS_ENDPOINT,
        required_env_vars=[GNANI_API_KEY_ENV],
        missing_env_vars=missing,
        default_stt_language="en-IN",
        supported_stt_languages=list(SUPPORTED_STT_LANGUAGES),
        supported_audio_formats=[ext.lstrip(".") for ext in SUPPORTED_AUDIO_EXTENSIONS],
        max_audio_bytes=MAX_AUDIO_UPLOAD_BYTES,
        default_tts_model="timbre-v2.5",
        default_tts_voice="Kaveri",
        rate_limit_max_requests=max_requests,
        rate_limit_window_seconds=window_seconds,
        message=message,
    )


def validate_stt_audio_upload(
    audio_bytes: bytes,
    filename: Optional[str],
    content_type: Optional[str],
    language_code: str,
) -> tuple[str, str]:
    """Validate audio payload size, format extension, MIME type, and language code."""
    if language_code not in SUPPORTED_STT_LANGUAGES:
        raise GnaniValidationError(
            status_code=400,
            error_code="UNSUPPORTED_LANGUAGE",
            message=(
                f"Unsupported language_code '{language_code}'. "
                f"Supported codes: {', '.join(SUPPORTED_STT_LANGUAGES)}."
            ),
        )

    if not audio_bytes or len(audio_bytes) == 0:
        raise GnaniValidationError(
            status_code=400,
            error_code="EMPTY_AUDIO_UPLOAD",
            message="Uploaded audio file is empty (0 bytes).",
        )

    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise GnaniValidationError(
            status_code=413,
            error_code="AUDIO_TOO_LARGE",
            message=(
                f"Uploaded audio ({len(audio_bytes)} bytes) exceeds the maximum allowed size "
                f"of {MAX_AUDIO_UPLOAD_BYTES} bytes (5 MB)."
            ),
        )

    clean_name = Path(filename or "recording.wav").name
    ext = Path(clean_name).suffix.lower()
    normalized_ct = (content_type or "").split(";")[0].strip().lower()

    ext_ok = ext in SUPPORTED_AUDIO_EXTENSIONS
    ct_ok = normalized_ct in SUPPORTED_AUDIO_CONTENT_TYPES

    if not ext_ok and not ct_ok:
        raise GnaniValidationError(
            status_code=415,
            error_code="UNSUPPORTED_AUDIO_FORMAT",
            message=(
                f"Unsupported audio format (filename='{clean_name}', content_type='{normalized_ct}'). "
                f"Gnani STT REST accepts WAV, MP3, OGG, FLAC, AAC, or M4A."
            ),
        )

    if normalized_ct and not ct_ok:
        raise GnaniValidationError(
            status_code=415,
            error_code="UNSUPPORTED_AUDIO_CONTENT_TYPE",
            message=(
                f"Unsupported audio media type '{normalized_ct}'. "
                f"Accepted formats: WAV, MP3, OGG, FLAC, AAC, M4A."
            ),
        )

    if ext and not ext_ok:
        raise GnaniValidationError(
            status_code=415,
            error_code="UNSUPPORTED_AUDIO_EXTENSION",
            message=(
                f"Unsupported file extension '{ext}'. "
                f"Accepted extensions: {', '.join(SUPPORTED_AUDIO_EXTENSIONS)}."
            ),
        )

    effective_filename = clean_name if ext_ok else f"recording.wav"
    effective_ct = normalized_ct if ct_ok else "audio/wav"
    return effective_filename, effective_ct


def _extract_upstream_error_message(response: httpx.Response, secret: str) -> str:
    """Extract a safe error description from a non-200 Gnani API response."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict) and isinstance(err.get("message"), str):
                return _redact_secret(err["message"], secret)
            if isinstance(payload.get("message"), str):
                return _redact_secret(payload["message"], secret)
    except Exception:  # noqa: BLE001
        pass
    return f"Upstream Gnani API returned HTTP {response.status_code}."


def _map_upstream_http_error(
    response: httpx.Response,
    secret: str,
    operation_label: str,
) -> GnaniUpstreamError:
    """Translate upstream Gnani HTTP error codes into safe GnaniUpstreamError exceptions."""
    status = response.status_code
    detail = _extract_upstream_error_message(response, secret)

    if status in (401, 403):
        return GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_AUTH_ERROR",
            message=(
                f"Gnani AI rejected the server credentials during {operation_label} "
                f"(upstream HTTP {status}). Check that {GNANI_API_KEY_ENV} is valid and active."
            ),
        )
    if status == 400:
        return GnaniUpstreamError(
            status_code=400,
            error_code="GNANI_INVALID_REQUEST",
            message=f"Gnani AI rejected the {operation_label} request: {detail}",
        )
    if status == 429:
        return GnaniUpstreamError(
            status_code=429,
            error_code="GNANI_RATE_LIMIT",
            message=f"Gnani AI rate limit exceeded during {operation_label}. Please wait and retry.",
        )
    return GnaniUpstreamError(
        status_code=503,
        error_code="GNANI_SERVICE_UNAVAILABLE",
        message=f"Gnani AI {operation_label} service is currently unavailable (upstream HTTP {status}).",
    )


def transcribe_speech_with_gnani(
    audio_bytes: bytes,
    filename: Optional[str] = "recording.wav",
    content_type: Optional[str] = "audio/wav",
    language_code: str = "en-IN",
    stt_format: str = "transcribe",
    http_client: Optional[httpx.Client] = None,
) -> STTResponseModel:
    """Transcribe short audio via Gnani Prisma v2.5 STT REST API (POST /stt/v3)."""
    effective_filename, effective_ct = validate_stt_audio_upload(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=content_type,
        language_code=language_code,
    )

    if stt_format not in ("transcribe", "verbatim"):
        raise GnaniValidationError(
            status_code=400,
            error_code="INVALID_STT_FORMAT",
            message="format must be 'transcribe' or 'verbatim'.",
        )

    api_key = _get_api_key()
    if not api_key:
        raise GnaniConfigurationError()

    url = f"{_get_base_url()}{GNANI_STT_ENDPOINT}"
    headers = {GNANI_AUTH_HEADER: api_key}
    files = {"audio_file": (effective_filename, audio_bytes, effective_ct)}
    data = {"language_code": language_code, "format": stt_format}
    timeout = _get_timeout_seconds()

    try:
        if http_client is not None:
            response = http_client.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=timeout,
            )
        else:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                )
    except httpx.TimeoutException as exc:
        raise GnaniUpstreamError(
            status_code=504,
            error_code="GNANI_STT_TIMEOUT",
            message="Gnani AI Speech-to-Text request timed out before completing.",
        ) from exc
    except httpx.RequestError as exc:
        raise GnaniUpstreamError(
            status_code=503,
            error_code="GNANI_STT_NETWORK_ERROR",
            message="Unable to reach Gnani AI Speech-to-Text service.",
        ) from exc

    if response.status_code != 200:
        raise _map_upstream_http_error(response, api_key, "Speech-to-Text")

    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_STT_MALFORMED_JSON",
            message="Gnani AI Speech-to-Text returned a malformed non-JSON response.",
        ) from exc

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_STT_UNSUCCESSFUL_PAYLOAD",
            message="Gnani AI Speech-to-Text returned an unsuccessful response payload.",
        )

    transcript = payload.get("transcript")
    if not isinstance(transcript, str):
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_STT_MISSING_TRANSCRIPT",
            message="Gnani AI Speech-to-Text response did not contain a valid transcript string.",
        )

    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    timestamp = payload.get("timestamp") if isinstance(payload.get("timestamp"), str) else None

    return STTResponseModel(
        transcript=transcript.strip(),
        language_code=language_code,
        request_id=request_id,
        timestamp=timestamp,
    )


def build_spoken_summary_from_report(report: VerificationRunReport) -> str:
    """Build a concise, factual spoken summary from an actual VerificationRunReport.

    Never alters the verification status or reads the entire Evidence Ledger aloud.
    """
    status = report.overall_status.value
    impl_name = report.implementation_name
    counts = report.counts

    if report.overall_status == VerificationStatus.PASS:
        reason = (
            f"All {counts.passed_checks} of {counts.total_checks} executed checks "
            f"and all {counts.passed_requirements} requirements passed."
        )
    elif report.overall_status == VerificationStatus.FAIL:
        failed_ids = [ev.test_id for ev in report.evidence if ev.observed_result == VerificationStatus.FAIL]
        failed_preview = ", ".join(failed_ids[:3])
        reason = (
            f"{counts.failed_checks} of {counts.total_checks} checks failed, "
            f"including {failed_preview}, causing {counts.failed_requirements} of "
            f"{counts.total_requirements} requirements to fail."
        )
    else:
        reason = (
            f"Coverage is incomplete: {counts.executed_checks} of {counts.total_checks} checks "
            f"were executed and {counts.unknown_checks} checks remain unexecuted or unknown."
        )

    unknown_note = ""
    if counts.unknown_checks > 0 and report.overall_status != VerificationStatus.UNKNOWN:
        unknown_note = f" Note that {counts.unknown_checks} check(s) remain unexecuted and unknown."

    summary = (
        f"PROOFLOOP verification result for {impl_name}: overall status is {status}. "
        f"{reason}{unknown_note} "
        f"Inspect the Evidence Ledger on screen for full check inputs and outputs."
    )
    return summary[:MAX_TTS_TEXT_LENGTH]


def validate_tts_parameters(
    text: str,
    model: str,
    voice: str,
    language: str,
    speed: float,
) -> str:
    """Validate TTS input text, model, voice catalog match, language, and speed."""
    cleaned_text = text.strip()
    if not cleaned_text:
        raise GnaniValidationError(
            status_code=400,
            error_code="EMPTY_TTS_TEXT",
            message="TTS text must not be empty.",
        )
    if len(cleaned_text) > MAX_TTS_TEXT_LENGTH:
        raise GnaniValidationError(
            status_code=400,
            error_code="TTS_TEXT_TOO_LONG",
            message=f"TTS text exceeds maximum length of {MAX_TTS_TEXT_LENGTH} characters.",
        )

    if model not in SUPPORTED_TTS_MODELS:
        raise GnaniValidationError(
            status_code=400,
            error_code="UNSUPPORTED_TTS_MODEL",
            message=(
                f"Unsupported Gnani TTS model '{model}'. "
                f"Supported models: {', '.join(sorted(SUPPORTED_TTS_MODELS.keys()))}."
            ),
        )

    allowed_voices = SUPPORTED_TTS_MODELS[model]
    if voice not in allowed_voices:
        raise GnaniValidationError(
            status_code=400,
            error_code="UNSUPPORTED_TTS_VOICE",
            message=(
                f"Voice '{voice}' is not supported by model '{model}'. "
                f"Choose a documented {model} voice."
            ),
        )

    if language not in SUPPORTED_TTS_LANGUAGES:
        raise GnaniValidationError(
            status_code=400,
            error_code="UNSUPPORTED_TTS_LANGUAGE",
            message=f"Unsupported Gnani TTS language '{language}'.",
        )

    if not (0.85 <= speed <= 1.15):
        raise GnaniValidationError(
            status_code=400,
            error_code="INVALID_TTS_SPEED",
            message="TTS speed must be between 0.85 and 1.15.",
        )

    return cleaned_text


def validate_tts_wav_response(audio_bytes: bytes, content_type_header: str) -> None:
    """Validate that the upstream Gnani TTS response is a genuine, bounded WAV audio payload."""
    normalized_ct = (content_type_header or "").split(";")[0].strip().lower()
    if normalized_ct not in ACCEPTED_TTS_WAV_CONTENT_TYPES:
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_TTS_INVALID_CONTENT_TYPE",
            message=(
                f"Gnani AI Text-to-Speech returned unexpected Content-Type '{normalized_ct or 'missing'}' "
                "instead of 'audio/wav'."
            ),
        )

    if not audio_bytes or len(audio_bytes) < MIN_WAV_HEADER_BYTES:
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_TTS_MALFORMED_AUDIO",
            message="Gnani AI Text-to-Speech returned an empty or truncated audio payload.",
        )

    if len(audio_bytes) > MAX_TTS_AUDIO_RESPONSE_BYTES:
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_TTS_OVERSIZED_AUDIO",
            message=(
                f"Gnani AI Text-to-Speech response ({len(audio_bytes)} bytes) exceeds "
                f"maximum allowed size of {MAX_TTS_AUDIO_RESPONSE_BYTES} bytes."
            ),
        )

    if audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        raise GnaniUpstreamError(
            status_code=502,
            error_code="GNANI_TTS_MALFORMED_AUDIO",
            message="Gnani AI Text-to-Speech response lacks a valid RIFF/WAVE binary header.",
        )


def synthesize_speech_with_gnani(
    summary_text: str,
    run_id: str,
    overall_status: VerificationStatus,
    model: str = "timbre-v2.5",
    voice: str = "Kaveri",
    language: str = "en-IN",
    speed: float = 1.0,
    http_client: Optional[httpx.Client] = None,
) -> TTSResponseModel:
    """Synthesize speech via Gnani Timbre TTS REST API (POST /api/v1/tts/inference)."""
    validated_text = validate_tts_parameters(
        text=summary_text,
        model=model,
        voice=voice,
        language=language,
        speed=speed,
    )

    api_key = _get_api_key()
    if not api_key:
        raise GnaniConfigurationError()

    url = f"{_get_base_url()}{GNANI_TTS_ENDPOINT}"
    headers = {
        GNANI_AUTH_HEADER: api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": validated_text,
        "voice": voice,
        "model": model,
        "language": language,
        "speed": speed,
        "audio_config": {
            "sample_rate": 48000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    timeout = _get_timeout_seconds()

    try:
        if http_client is not None:
            response = http_client.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        else:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
    except httpx.TimeoutException as exc:
        raise GnaniUpstreamError(
            status_code=504,
            error_code="GNANI_TTS_TIMEOUT",
            message="Gnani AI Text-to-Speech request timed out before completing.",
        ) from exc
    except httpx.RequestError as exc:
        raise GnaniUpstreamError(
            status_code=503,
            error_code="GNANI_TTS_NETWORK_ERROR",
            message="Unable to reach Gnani AI Text-to-Speech service.",
        ) from exc

    if response.status_code != 200:
        raise _map_upstream_http_error(response, api_key, "Text-to-Speech")

    audio_bytes = response.content
    content_type_header = response.headers.get("content-type", "")
    validate_tts_wav_response(audio_bytes=audio_bytes, content_type_header=content_type_header)

    encoded_audio = base64.b64encode(audio_bytes).decode("ascii")
    return TTSResponseModel(
        summary_text=validated_text,
        audio_base64=encoded_audio,
        content_type="audio/wav",
        run_id=run_id,
        overall_status=overall_status,
        model=model,
        voice=voice,
        language=language,
    )

