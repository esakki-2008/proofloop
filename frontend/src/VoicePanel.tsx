import React, { useEffect, useRef, useState } from 'react';
import {
  synthesizeVerificationSummary,
  transcribeRequirementAudio,
} from './api';
import {
  GnaniConfigStatus,
  TTSResponse,
  VerificationRunReport,
} from './types';
import { StatusBadge } from './App';

export const LANGUAGE_LABELS: Record<string, string> = {
  'en-IN': 'English (en-IN)',
  'hi-IN': 'Hindi (hi-IN)',
  'ta-IN': 'Tamil (ta-IN)',
  'te-IN': 'Telugu (te-IN)',
  'kn-IN': 'Kannada (kn-IN)',
  'ml-IN': 'Malayalam (ml-IN)',
  'mr-IN': 'Marathi (mr-IN)',
  'bn-IN': 'Bengali (bn-IN)',
  'gu-IN': 'Gujarati (gu-IN)',
  'pa-IN': 'Punjabi (pa-IN)',
};

export function assessTranscriptScope(transcript: string): {
  matchesFixedTask: boolean;
  guidance: string;
} {
  const normalized = transcript.toLowerCase();
  const gradingKeywords = [
    'mark',
    'subject',
    '40',
    '39',
    'pass',
    'fail',
    'student',
    'grade',
    'grading',
    'average',
    'boundary',
    'empty',
  ];
  const matches = gradingKeywords.some((kw) => normalized.includes(kw));
  if (matches) {
    return {
      matchesFixedTask: true,
      guidance:
        'Confirmed transcript aligns with the supported Student-Grading verification task (every subject mark >= 40, REQ-01 through REQ-03). Run verification above to execute the predefined checks.',
    };
  }
  return {
    matchesFixedTask: false,
    guidance:
      'Scope limitation: PROOFLOOP currently verifies only the predefined Student-Grading implementations (every subject mark >= 40) and does not dynamically generate test suites or execute arbitrary code from spoken requests.',
  };
}

/**
 * Convert an AudioBuffer into a standard 16-bit PCM WAV Blob so browser recordings
 * are always sent in a format officially supported by Gnani STT REST (/stt/v3).
 */
function encodeAudioBufferToWavBlob(audioBuffer: AudioBuffer): Blob {
  const numChannels = 1;
  const sampleRate = audioBuffer.sampleRate || 16000;
  const channelData = audioBuffer.getChannelData(0);
  const numSamples = channelData.length;
  const bytesPerSample = 2;
  const dataSize = numSamples * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i += 1) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
  view.setUint16(32, numChannels * bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i += 1) {
    const clamped = Math.max(-1, Math.min(1, channelData[i]));
    view.setInt16(
      offset,
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
      true,
    );
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

async function normalizeRecordedBlobToSupportedFormat(rawBlob: Blob): Promise<{
  blob: Blob;
  filename: string;
}> {
  const mime = (rawBlob.type || '').toLowerCase();
  if (mime.includes('wav')) {
    return { blob: new Blob([rawBlob], { type: 'audio/wav' }), filename: 'recording.wav' };
  }
  if (mime.includes('ogg')) {
    return { blob: new Blob([rawBlob], { type: 'audio/ogg' }), filename: 'recording.ogg' };
  }
  if (mime.includes('mp4') || mime.includes('m4a')) {
    return { blob: new Blob([rawBlob], { type: 'audio/mp4' }), filename: 'recording.m4a' };
  }
  if (mime.includes('mpeg') || mime.includes('mp3')) {
    return { blob: new Blob([rawBlob], { type: 'audio/mpeg' }), filename: 'recording.mp3' };
  }

  if (typeof window !== 'undefined' && 'AudioContext' in window) {
    const AudioCtx = window.AudioContext;
    const ctx = new AudioCtx();
    try {
      const arrayBuffer = await rawBlob.arrayBuffer();
      const decoded = await ctx.decodeAudioData(arrayBuffer);
      return {
        blob: encodeAudioBufferToWavBlob(decoded),
        filename: 'recording.wav',
      };
    } finally {
      await ctx.close().catch(() => undefined);
    }
  }

  return {
    blob: new Blob([rawBlob], { type: 'audio/wav' }),
    filename: 'recording.wav',
  };
}

export interface VoicePanelProps {
  voiceStatus: GnaniConfigStatus | null;
  activeRun: VerificationRunReport;
  selectedLanguage?: string;
  onLanguageChange?: (language: string) => void;
  onTranscriptConfirmed?: (transcript: string) => void;
}

export function VoicePanel({
  voiceStatus,
  activeRun,
  selectedLanguage: controlledLanguage,
  onLanguageChange,
  onTranscriptConfirmed,
}: VoicePanelProps) {
  const [internalLanguage, setInternalLanguage] = useState<string>('en-IN');
  const selectedLanguage = controlledLanguage ?? internalLanguage;

  const handleLanguageSelect = (lang: string) => {
    setInternalLanguage(lang);
    onLanguageChange?.(lang);
  };

  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);
  const [transcriptDraft, setTranscriptDraft] = useState<string>('');
  const [confirmedTranscript, setConfirmedTranscript] = useState<string | null>(null);
  const [sttError, setSttError] = useState<string | null>(null);
  const [sttRequestId, setSttRequestId] = useState<string | null>(null);

  const [isSynthesizing, setIsSynthesizing] = useState<boolean>(false);
  const [ttsResult, setTtsResult] = useState<TTSResponse | null>(null);
  const [ttsError, setTtsError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const cancelledRef = useRef<boolean>(false);

  const releaseMediaResources = () => {
    if (mediaStreamRef.current) {
      for (const track of mediaStreamRef.current.getTracks()) {
        track.stop();
      }
      mediaStreamRef.current = null;
    }
    mediaRecorderRef.current = null;
  };

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      releaseMediaResources();
    };
  }, []);

  // Clear stale TTS result if the user switches to a different verification run
  useEffect(() => {
    setTtsResult(null);
    setTtsError(null);
  }, [activeRun.run_id]);

  const isGnaniConfigured = Boolean(voiceStatus?.configured);

  const handleUploadAndTranscribe = async (blob: Blob, filename: string) => {
    setIsTranscribing(true);
    setSttError(null);
    try {
      const response = await transcribeRequirementAudio(blob, filename, selectedLanguage);
      setTranscriptDraft(response.transcript);
      setConfirmedTranscript(null);
      setSttRequestId(response.request_id);
    } catch (err) {
      setSttError(
        err instanceof Error ? err.message : 'Speech-to-text transcription failed.',
      );
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleStartRecording = async () => {
    if (isRecording || isTranscribing || !isGnaniConfigured) return;
    setSttError(null);

    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== 'function' ||
      typeof MediaRecorder === 'undefined'
    ) {
      setSttError(
        'Microphone recording is not supported in this browser environment. Upload a supported audio file or enter requirement text directly.',
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      chunksRef.current = [];
      cancelledRef.current = false;

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const wasCancelled = cancelledRef.current;
        const recordedChunks = [...chunksRef.current];
        const recorderMime = recorder.mimeType || 'audio/wav';
        releaseMediaResources();
        setIsRecording(false);

        if (wasCancelled || recordedChunks.length === 0) {
          return;
        }

        try {
          const rawBlob = new Blob(recordedChunks, { type: recorderMime });
          const { blob, filename } = await normalizeRecordedBlobToSupportedFormat(rawBlob);
          await handleUploadAndTranscribe(blob, filename);
        } catch (err) {
          setSttError(
            err instanceof Error ? err.message : 'Failed to process recorded audio.',
          );
        }
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      releaseMediaResources();
      setIsRecording(false);
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setSttError(
          'Microphone permission was denied. Grant microphone access in your browser or upload an audio file.',
        );
      } else {
        setSttError(
          err instanceof Error
            ? `Microphone access failed: ${err.message}`
            : 'Microphone access failed.',
        );
      }
    }
  };

  const handleStopRecording = () => {
    if (!mediaRecorderRef.current || !isRecording) return;
    cancelledRef.current = false;
    mediaRecorderRef.current.stop();
  };

  const handleCancelRecording = () => {
    cancelledRef.current = true;
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    } else {
      releaseMediaResources();
      setIsRecording(false);
    }
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || isTranscribing || !isGnaniConfigured) return;
    await handleUploadAndTranscribe(file, file.name);
  };

  const handleConfirmTranscript = () => {
    const trimmed = transcriptDraft.trim();
    if (!trimmed) return;
    setConfirmedTranscript(trimmed);
    onTranscriptConfirmed?.(trimmed);
  };

  const handleReadResultAloud = async () => {
    if (isSynthesizing || !isGnaniConfigured) return;
    setIsSynthesizing(true);
    setTtsError(null);
    try {
      const response = await synthesizeVerificationSummary(
        activeRun.run_id,
        selectedLanguage,
        'Kaveri',
        'timbre-v2.5',
      );
      setTtsResult(response);
    } catch (err) {
      setTtsError(
        err instanceof Error ? err.message : 'Text-to-speech synthesis failed.',
      );
    } finally {
      setIsSynthesizing(false);
    }
  };

  const scopeAssessment = confirmedTranscript
    ? assessTranscriptScope(confirmedTranscript)
    : null;

  return (
    <section
      className="surface-card voice-panel-card"
      aria-labelledby="voice-panel-heading"
      data-testid="gnani-voice-panel"
    >
      <div className="section-header">
        <div>
          <div className="eyebrow-tag">Optional Voice Interface • Gnani AI</div>
          <h2 id="voice-panel-heading" className="section-title">
            Gnani AI Speech Integration (Prisma STT &amp; Timbre TTS)
          </h2>
          <p className="section-subtitle">
            Transcribe a spoken requirement for human review or generate a spoken summary from
            the stored verification report. Voice never alters verification outcomes or
            executes code.
          </p>
        </div>
        <span
          className={`status-badge ${isGnaniConfigured ? 'status-PASS' : 'status-UNKNOWN'}`}
          data-testid="gnani-config-badge"
        >
          {isGnaniConfigured
            ? 'Gnani AI: Configured'
            : 'Gnani AI: Unconfigured (Set GNANI_API_KEY)'}
        </span>
      </div>

      {!isGnaniConfigured && (
        <div
          role="status"
          data-testid="gnani-unconfigured-notice"
          className="notice-banner notice-warning"
        >
          <strong>Voice API Unavailable:</strong>{' '}
          {voiceStatus?.message ||
            'Set GNANI_API_KEY on the backend to enable live Gnani AI Prisma STT and Timbre TTS.'}{' '}
          PROOFLOOP works normally without voice: you can review or edit requirement text
          manually and run all deterministic verification checks.
        </div>
      )}

      <div className="voice-grid">
        {/* Left column: STT Speak Requirement + Editable Transcript + Explicit Confirmation */}
        <div className="voice-subpanel">
          <div className="voice-subpanel-header">
            <strong>1. Speak or Edit Requirement (Gnani Prisma v2.5 STT)</strong>
            <div className="inline-control-group">
              <label htmlFor="gnani-lang-select" className="control-label">
                Language:
              </label>
              <select
                id="gnani-lang-select"
                className="control-select"
                value={selectedLanguage}
                onChange={(e) => handleLanguageSelect(e.target.value)}
                disabled={isRecording || isTranscribing}
              >
                {(voiceStatus?.supported_stt_languages ?? Object.keys(LANGUAGE_LABELS)).map(
                  (code) => (
                    <option key={code} value={code}>
                      {LANGUAGE_LABELS[code] || code}
                    </option>
                  ),
                )}
              </select>
            </div>
          </div>

          <div className="voice-action-row">
            {!isRecording ? (
              <button
                type="button"
                className="btn btn-secondary"
                data-testid="speak-requirement-btn"
                onClick={handleStartRecording}
                disabled={!isGnaniConfigured || isTranscribing}
              >
                {isTranscribing ? 'Transcribing with Gnani STT...' : 'Speak Requirement'}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="btn"
                  data-testid="stop-recording-btn"
                  onClick={handleStopRecording}
                >
                  Stop &amp; Transcribe
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  data-testid="cancel-recording-btn"
                  onClick={handleCancelRecording}
                >
                  Cancel Recording
                </button>
                <span className="mono recording-pill" data-testid="recording-indicator">
                  Recording microphone audio...
                </span>
              </>
            )}

            <label
              className={`btn btn-secondary file-upload-btn ${
                !isGnaniConfigured || isRecording || isTranscribing ? 'is-disabled' : ''
              }`}
            >
              Upload Audio Clip
              <input
                type="file"
                accept=".wav,.mp3,.ogg,.flac,.aac,.m4a,audio/wav,audio/mpeg,audio/ogg,audio/flac,audio/aac,audio/mp4"
                data-testid="audio-upload-input"
                onChange={handleFileChange}
                disabled={!isGnaniConfigured || isRecording || isTranscribing}
                style={{ display: 'none' }}
              />
            </label>
          </div>

          {sttError && (
            <div
              role="alert"
              data-testid="stt-error-message"
              className="notice-banner notice-error"
            >
              <strong>STT Error:</strong> {sttError}
            </div>
          )}

          <div className="field-block">
            <label htmlFor="requirement-transcript-input" className="field-label">
              Editable Requirement Statement (Confirm before applying to review):
            </label>
            <textarea
              id="requirement-transcript-input"
              aria-label="Requirement Transcript"
              data-testid="transcript-textarea"
              className="control-textarea"
              rows={3}
              value={transcriptDraft}
              onChange={(e) => {
                setTranscriptDraft(e.target.value);
                setConfirmedTranscript(null);
              }}
              placeholder="Transcribed speech appears here, or type/edit a requirement statement before confirming..."
            />
          </div>

          <div className="voice-footer-row">
            <button
              type="button"
              className="btn btn-secondary"
              data-testid="confirm-transcript-btn"
              onClick={handleConfirmTranscript}
              disabled={!transcriptDraft.trim()}
            >
              Confirm Transcript for Review
            </button>
            {sttRequestId && (
              <span className="mono muted-meta">Gnani Request ID: {sttRequestId}</span>
            )}
          </div>

          {confirmedTranscript && scopeAssessment && (
            <div
              data-testid="confirmed-transcript-banner"
              className="confirmed-transcript-card"
            >
              <div className="confirmed-transcript-header">
                <strong>Confirmed Transcript (Human Review Only)</strong>
                <span className="mono scope-tag">
                  {scopeAssessment.matchesFixedTask
                    ? 'Aligned with Fixed Grading Task'
                    : 'Outside Fixed Task Scope'}
                </span>
              </div>
              <p className="confirmed-quote">&ldquo;{confirmedTranscript}&rdquo;</p>
              <p className="confirmed-guidance">{scopeAssessment.guidance}</p>
            </div>
          )}
        </div>

        {/* Right column: TTS Read Verification Result Aloud */}
        <div className="voice-subpanel">
          <div className="voice-subpanel-header">
            <strong>2. Read Verification Result Aloud (Gnani Timbre v2.5 TTS)</strong>
            <StatusBadge status={activeRun.overall_status} prefix="Active Verdict" />
          </div>

          <p className="voice-desc">
            Synthesizes a spoken summary from the stored backend verification report for{' '}
            <code className="mono">{activeRun.implementation_short_label}</code> (
            <strong>{activeRun.run_label}</strong>).
          </p>

          <div className="voice-action-row">
            <button
              type="button"
              className="btn btn-secondary"
              data-testid="read-result-aloud-btn"
              onClick={handleReadResultAloud}
              disabled={!isGnaniConfigured || isSynthesizing}
            >
              {isSynthesizing ? 'Synthesizing Speech...' : 'Read Result Aloud'}
            </button>
            <span className="mono muted-meta">
              Model: {voiceStatus?.default_tts_model || 'timbre-v2.5'} • Voice:{' '}
              {voiceStatus?.default_tts_voice || 'Kaveri'}
            </span>
          </div>

          {ttsError && (
            <div
              role="alert"
              data-testid="tts-error-message"
              className="notice-banner notice-error"
            >
              <strong>TTS Error:</strong> {ttsError}
            </div>
          )}

          {ttsResult && (
            <div data-testid="tts-summary-box" className="tts-result-card">
              <div className="confirmed-transcript-header">
                <strong>Synthesized Spoken Summary</strong>
                {ttsResult.overall_status && (
                  <StatusBadge status={ttsResult.overall_status} prefix="Verified Status" />
                )}
              </div>
              <p data-testid="tts-summary-text" className="tts-summary-copy">
                {ttsResult.summary_text}
              </p>
              <audio
                controls
                preload="metadata"
                data-testid="tts-audio-player"
                src={`data:${ttsResult.content_type};base64,${ttsResult.audio_base64}`}
                className="tts-audio-element"
              >
                Your browser does not support the HTML5 audio element.
              </audio>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
