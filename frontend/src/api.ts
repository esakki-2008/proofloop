import {
  CatalogResponse,
  EvidenceLedger,
  GnaniConfigStatus,
  STTResponse,
  TTSResponse,
  VerificationRunReport,
} from './types';

export async function fetchCatalog(): Promise<CatalogResponse> {
  const response = await fetch('/api/catalog');
  if (!response.ok) {
    throw new Error(`Failed to load verification catalog (HTTP ${response.status})`);
  }
  return response.json() as Promise<CatalogResponse>;
}

export async function fetchLedger(): Promise<EvidenceLedger> {
  const response = await fetch('/api/ledger');
  if (!response.ok) {
    throw new Error(`Failed to load evidence ledger (HTTP ${response.status})`);
  }
  return response.json() as Promise<EvidenceLedger>;
}

export async function resetBaselineLedger(): Promise<EvidenceLedger> {
  const response = await fetch('/api/ledger/reset', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to reset evidence ledger (HTTP ${response.status})`);
  }
  return response.json() as Promise<EvidenceLedger>;
}

export async function triggerVerificationRun(
  implementationId: string,
  selectedTestIds: string[],
  runLabel?: string,
): Promise<VerificationRunReport> {
  const response = await fetch('/api/verify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      implementation_id: implementationId,
      selected_test_ids: selectedTestIds,
      run_label: runLabel,
    }),
  });
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ detail: 'Verification request failed' }));
    throw new Error(errBody.detail || `Verification failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<VerificationRunReport>;
}

export async function fetchVoiceStatus(): Promise<GnaniConfigStatus> {
  const response = await fetch('/api/voice/status');
  if (!response.ok) {
    throw new Error(`Failed to load Gnani voice status (HTTP ${response.status})`);
  }
  return response.json() as Promise<GnaniConfigStatus>;
}

export async function transcribeRequirementAudio(
  audioBlob: Blob,
  filename: string = 'recording.wav',
  languageCode: string = 'en-IN',
): Promise<STTResponse> {
  const formData = new FormData();
  formData.append('audio_file', audioBlob, filename);
  formData.append('language_code', languageCode);
  formData.append('format', 'transcribe');

  const response = await fetch('/api/voice/stt', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ detail: 'Speech-to-text request failed' }));
    throw new Error(errBody.detail || `Speech-to-text failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<STTResponse>;
}

export async function synthesizeVerificationSummary(
  runId: string,
  language: string = 'en-IN',
  voice: string = 'Kaveri',
  model: string = 'timbre-v2.5',
): Promise<TTSResponse> {
  const response = await fetch('/api/voice/tts', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      run_id: runId,
      language,
      voice,
      model,
      speed: 1.0,
    }),
  });
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ detail: 'Text-to-speech request failed' }));
    throw new Error(errBody.detail || `Text-to-speech failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<TTSResponse>;
}

