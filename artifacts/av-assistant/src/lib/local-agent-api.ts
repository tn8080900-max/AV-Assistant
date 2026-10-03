const BASE = '/agent-api';

export type CompanionHealth = {
  online: boolean;
  providerReady?: boolean;
  providerName?: string;
};

export type AgentSettings = {
  allowed_directories: string[];
  allowed_applications: string[];
  provider_ready?: boolean;
  provider_name?: string;
  [key: string]: unknown;
};

export type AgentRunResult = {
  [key: string]: unknown;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    });
  } catch {
    throw new Error('The local companion could not be reached. Make sure it is running on this computer.');
  }
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = typeof body?.detail === 'string' ? body.detail : typeof body?.message === 'string' ? body.message : '';
    } catch {
      detail = '';
    }
    throw new Error(detail || `The local companion returned an error (${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
  if (!contentType.includes('json')) {
    throw new Error('The local companion did not return an API response. Make sure it is running on this computer.');
  }
  return response.json() as Promise<T>;
}

export const localAgentApi = {
  health: async (): Promise<CompanionHealth> => {
    const body = await request<Record<string, unknown>>('/health');
    return {
      online: true,
      providerReady: Boolean(body.provider_ready ?? body.providerReady ?? body.ready),
      providerName: String(body.provider_name ?? body.providerName ?? ''),
    };
  },
  getSettings: async (): Promise<AgentSettings> => {
    const body = await request<AgentSettings>('/settings');
    return {
      ...body,
      allowed_directories: Array.isArray(body.allowed_directories) ? body.allowed_directories : [],
      allowed_applications: Array.isArray(body.allowed_applications) ? body.allowed_applications : [],
    };
  },
  saveSettings: (data: Pick<AgentSettings, 'allowed_directories' | 'allowed_applications'>) =>
    request<AgentSettings>('/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  transcribe: async (audio: Blob): Promise<string> => {
    const form = new FormData();
    form.append('file', audio, 'recording.webm');
    const body = await request<Record<string, unknown>>('/voice/transcribe', { method: 'POST', body: form });
    const transcript = body.text ?? body.transcript ?? body.message;
    if (typeof transcript !== 'string') throw new Error('The transcription response did not include recognized text.');
    return transcript;
  },
  run: (message: string) =>
    request<AgentRunResult>('/agent/run', { method: 'POST', body: JSON.stringify({ message }) }),
  approve: (requestId: string, approved: boolean) =>
    request<AgentRunResult>(`/approvals/${encodeURIComponent(requestId)}`, {
      method: 'POST',
      body: JSON.stringify({ approved }),
    }),
  deleteSession: () => request<void>('/session', { method: 'DELETE' }),
  speak: async (text: string): Promise<Blob> => {
    let response: Response;
    try {
      response = await fetch(`${BASE}/voice/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
    } catch {
      throw new Error('The local companion could not be reached for audio playback.');
    }
    if (!response.ok) throw new Error(`Audio playback is unavailable (${response.status}).`);
    return response.blob();
  },
};