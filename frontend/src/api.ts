import { CatalogResponse, EvidenceLedger, VerificationRunReport } from './types';

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
