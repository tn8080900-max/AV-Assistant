import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
  Activity, AlertCircle, AudioLines, ChevronRight, CircleHelp, Clock3,
  Folder, Headphones, LockKeyhole, Menu, Mic, MicOff, MoreHorizontal, Plus,
  Send, Settings2, Shield, Terminal, UserRound, X,
} from 'lucide-react';
import { Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
import { localAgentApi, type AgentRunResult, type AgentSettings, type CompanionHealth } from '@/lib/local-agent-api';
import NotFound from '@/pages/not-found';

const queryClient = new QueryClient();
type AgentState = 'IDLE' | 'LISTENING' | 'TRANSCRIBING' | 'THINKING' | 'USING_TOOL' | 'WAITING_FOR_PERMISSION' | 'SPEAKING' | 'ERROR';
type Message = { id: string; role: 'user' | 'assistant'; content: string; createdAt: number };
type ToolActivity = { id: string; name: string; status: string; result?: string };
type PendingConfirmation = { requestId: string; title: string; details: string };

const busyStates: AgentState[] = ['TRANSCRIBING', 'THINKING', 'USING_TOOL', 'WAITING_FOR_PERMISSION'];
const statusCopy: Record<AgentState, string> = {
  IDLE: 'Ready when you are',
  LISTENING: 'Listening to your voice',
  TRANSCRIBING: 'Turning speech into text',
  THINKING: 'Considering your request',
  USING_TOOL: 'Working with a local tool',
  WAITING_FOR_PERMISSION: 'Your permission is needed',
  SPEAKING: 'Speaking response',
  ERROR: 'Something needs attention',
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function describeResult(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  try { return JSON.stringify(value); } catch { return String(value); }
}

function parseRunResult(result: AgentRunResult): {
  text: string;
  tools: ToolActivity[];
  confirmation?: PendingConfirmation;
  state: AgentState;
} {
  const response = asRecord(result);
  const text = String(response.response ?? response.message ?? response.text ?? response.assistant_message ?? '');
  const rawTools = response.tools ?? response.tool_activity ?? response.activities;
  const tools: ToolActivity[] = Array.isArray(rawTools) ? rawTools.map((raw, index) => {
    const tool = asRecord(raw);
    return {
      id: String(tool.id ?? `${Date.now()}-${index}`),
      name: String(tool.name ?? tool.tool ?? 'Local tool'),
      status: String(tool.status ?? 'complete'),
      result: describeResult(tool.result ?? tool.output),
    };
  }) : [];
  const rawConfirmation = asRecord(response.pending_confirmation ?? response.pendingConfirmation ?? response.confirmation);
  const id = rawConfirmation.request_id ?? rawConfirmation.requestId ?? rawConfirmation.id;
  const confirmation = id ? {
    requestId: String(id),
    title: String(rawConfirmation.title ?? rawConfirmation.action ?? 'Permission requested'),
    details: String(rawConfirmation.details ?? rawConfirmation.description ?? rawConfirmation.message ?? 'The local companion is requesting permission to continue.'),
  } : undefined;
  const rawState = String(response.state ?? '').toUpperCase();
  return {
    text,
    tools,
    confirmation,
    state: confirmation ? 'WAITING_FOR_PERMISSION' : rawState === 'USING_TOOL' ? 'USING_TOOL' : 'IDLE',
  };
}

function App() {
  const [agentState, setAgentState] = useState<AgentState>('IDLE');
  const [health, setHealth] = useState<CompanionHealth | null>(null);
  const [healthError, setHealthError] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [activities, setActivities] = useState<ToolActivity[]>([]);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const [draft, setDraft] = useState('');
  const [reviewText, setReviewText] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [isSettingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [newDirectory, setNewDirectory] = useState('');
  const [newApplication, setNewApplication] = useState('');
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef('');
  const [audioBusy, setAudioBusy] = useState(false);

  const checkHealth = useCallback(async () => {
    try {
      const status = await localAgentApi.health();
      setHealth(status);
      setHealthError('');
    } catch (cause) {
      setHealth({ online: false });
      setHealthError(cause instanceof Error ? cause.message : 'Local companion is offline.');
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    const timer = window.setInterval(() => { void checkHealth(); }, 12000);
    return () => window.clearInterval(timer);
  }, [checkHealth]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    activeAudioRef.current?.pause();
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
  }, []);

  const loadSettings = async () => {
    setSettingsLoading(true);
    setSettingsError('');
    try {
      setSettings(await localAgentApi.getSettings());
    } catch (cause) {
      setSettingsError(cause instanceof Error ? cause.message : 'Could not load local settings.');
    } finally {
      setSettingsLoading(false);
    }
  };

  const openSettings = () => {
    setSettingsOpen(true);
    void loadSettings();
  };

  const addMessage = (role: Message['role'], content: string) => {
    const message = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, role, content, createdAt: Date.now() };
    setMessages((existing) => [...existing, message]);
    return message;
  };

  const speakResponse = async (text: string) => {
    if (!text.trim()) return;
    try {
      const blob = await localAgentApi.speak(text);
      const url = URL.createObjectURL(blob);
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = url;
      const audio = new Audio(url);
      activeAudioRef.current = audio;
      setAgentState('SPEAKING');
      audio.onended = () => {
        setAgentState((current) => current === 'SPEAKING' ? 'IDLE' : current);
        setAudioBusy(false);
      };
      audio.onerror = () => {
        setAgentState((current) => current === 'SPEAKING' ? 'IDLE' : current);
        setAudioBusy(false);
      };
      setAudioBusy(true);
      await audio.play();
    } catch (cause) {
      setAudioBusy(false);
      setAgentState((current) => current === 'SPEAKING' ? 'IDLE' : current);
      if (cause instanceof Error) setError(cause.message);
    }
  };

  const applyResult = (result: AgentRunResult) => {
    const parsed = parseRunResult(result);
    if (parsed.tools.length) {
      setActivities((existing) => [...existing, ...parsed.tools]);
    }
    setPending(parsed.confirmation ?? null);
    if (parsed.text) {
      addMessage('assistant', parsed.text);
      if (!parsed.confirmation) void speakResponse(parsed.text);
      else setAgentState('WAITING_FOR_PERMISSION');
    } else {
      setAgentState(parsed.state);
    }
    if (!parsed.confirmation && !parsed.text) setAgentState('IDLE');
  };

  const submitMessage = async (messageText: string) => {
    const clean = messageText.trim();
    if (!clean || busyStates.includes(agentState) || !health?.online) return;
    setError('');
    setReviewText(null);
    setDraft('');
    addMessage('user', clean);
    setAgentState('THINKING');
    try {
      const result = await localAgentApi.run(clean);
      applyResult(result);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'The request could not be completed.';
      setError(message);
      setAgentState('ERROR');
    }
  };

  const startRecording = async () => {
    if (!health?.online) {
      setError('Connect the local companion before recording voice.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Voice recording is not available in this browser. You can still type your request below.');
      return;
    }
    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: BlobPart[] = [];
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        if (!chunks.length) {
          setAgentState('IDLE');
          return;
        }
        setAgentState('TRANSCRIBING');
        try {
          const transcript = await localAgentApi.transcribe(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }));
          setReviewText(transcript);
          setAgentState('IDLE');
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Voice transcription failed.');
          setAgentState('ERROR');
        }
      };
      recorder.start();
      setAgentState('LISTENING');
    } catch (cause) {
      const message = cause instanceof Error && cause.name === 'NotAllowedError'
        ? 'Microphone access was declined. Allow microphone access in your browser, or type your request instead.'
        : 'Could not start microphone recording. You can still type your request.';
      setError(message);
      setAgentState('ERROR');
    }
  };

  const stopRecording = () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  };

  const decidePermission = async (approved: boolean) => {
    if (!pending) return;
    const current = pending;
    setPending(null);
    setAgentState('USING_TOOL');
    setError('');
    try {
      const response = await localAgentApi.approve(current.requestId, approved);
      if (!approved) {
        setActivities((existing) => [...existing, {
          id: `${Date.now()}`, name: current.title, status: 'denied', result: 'You denied this request.',
        }]);
        const parsed = parseRunResult(response);
        if (parsed.text) {
          addMessage('assistant', parsed.text);
          void speakResponse(parsed.text);
        }
        setAgentState('IDLE');
      } else {
        applyResult(response);
      }
    } catch (cause) {
      setPending(current);
      setAgentState('WAITING_FOR_PERMISSION');
      setError(cause instanceof Error ? cause.message : 'The permission decision could not be sent.');
    }
  };

  const newSession = async () => {
    setError('');
    try {
      await localAgentApi.deleteSession();
      setMessages([]);
      setActivities([]);
      setPending(null);
      setDraft('');
      setReviewText(null);
      setAgentState('IDLE');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not clear the session.');
    }
  };

  const saveSettings = async () => {
    if (!settings) return;
    setSettingsSaving(true);
    setSettingsError('');
    try {
      const saved = await localAgentApi.saveSettings({
        allowed_directories: settings.allowed_directories,
        allowed_applications: settings.allowed_applications,
      });
      setSettings({ ...settings, ...saved });
    } catch (cause) {
      setSettingsError(cause instanceof Error ? cause.message : 'Could not save settings.');
    } finally {
      setSettingsSaving(false);
    }
  };

  const isBusy = busyStates.includes(agentState);
  const promptHistory = messages.filter((message) => message.role === 'user').slice(-5).reverse();
  const providerReady = health?.providerReady ?? Boolean(settings?.provider_ready);

  return (
    <div className="app-shell">
      <aside className="side-rail">
        <div className="brand">
          <div className="brand-mark"><AudioLines size={18} strokeWidth={2.2} /></div>
          <div><div className="brand-name">AV Assistant</div><div className="brand-caption">Personal agent</div></div>
        </div>
        <div className="rail-label">Workspace</div>
        <button className="rail-action active" type="button" aria-current="page" onClick={() => document.querySelector('.conversation-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })} data-testid="nav-conversation">
          <AudioLines /><span>Conversation</span>
        </button>
        <button className="rail-action" type="button" onClick={openSettings} data-testid="button-open-settings">
          <Settings2 /><span>Permissions & settings</span>
        </button>
        <div className="rail-history">
          <div className="rail-label">Recent requests</div>
          <div className="history-list">
            {promptHistory.length ? promptHistory.map((message) => (
              <button className="history-item" type="button" key={message.id} title={message.content}
                onClick={() => setDraft(message.content)} data-testid={`history-request-${message.id}`}>
                <Clock3 size={12} style={{ display: 'inline', marginRight: 7, verticalAlign: '-2px' }} />
                {message.content}
              </button>
            )) : <div className="history-item" style={{ cursor: 'default' }}>Your requests will appear here</div>}
          </div>
        </div>
        <div className="rail-bottom">
          <div className="privacy-note"><LockKeyhole size={14} /><span>Computer actions stay here. AI requests and voice recordings go to your configured providers.</span></div>
          <div className="profile-row">
            <div className="avatar-mark">S</div>
            <div className="profile-copy"><strong>Local session</strong>Private by design</div>
            <MoreHorizontal size={17} color="#7d857a" style={{ marginLeft: 'auto' }} />
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" type="button" aria-label="Open settings" onClick={openSettings} data-testid="button-mobile-menu"><Menu /></button>
          <div className="crumb">Your desktop companion <ChevronRight size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> Conversation</div>
          <div className="top-actions">
            <div className={`connection-pill ${health?.online ? '' : 'offline'}`} role="status" data-testid="status-companion">
              <span className="connection-dot" />{health?.online ? 'Local companion connected' : 'Companion offline'}
            </div>
            <button className="icon-button" type="button" aria-label="Start a new session" title="Clear session" onClick={newSession} data-testid="button-new-session"><Plus /></button>
            <button className="icon-button" type="button" aria-label="Settings" title="Permissions and settings" onClick={openSettings} data-testid="button-settings"><Settings2 /></button>
          </div>
        </header>

        <div className="page-content">
          {!health?.online && (
            <div className="status-banner" role="alert" data-testid="banner-companion-offline">
              <AlertCircle />
              <span><strong>Your local companion is offline.</strong> Start the FastAPI companion on this computer, then <button type="button" onClick={() => void checkHealth()}>try again</button>. Local computer tools are never run from a hosted server.</span>
            </div>
          )}
          {error && (
            <div className="status-banner" role="alert" data-testid="banner-error">
              <AlertCircle /><span>{error}</span><button type="button" aria-label="Dismiss error" onClick={() => { setError(''); if (agentState === 'ERROR') setAgentState('IDLE'); }} style={{ marginLeft: 'auto', border: 0, background: 'transparent' }}><X size={14} /></button>
            </div>
          )}
          <div className="welcome-row">
            <div><div className="eyebrow">At your side, not in the way</div><h1 className="welcome-title">What can I take care of?</h1><p className="welcome-sub">Speak naturally, or write a request. You stay in control of every action.</p></div>
            <div className="session-meta" data-testid="text-session-state">{statusCopy[agentState]}</div>
          </div>

          <div className="workspace-grid">
            <section className="conversation-card" aria-label="Conversation">
              <div className="conversation-head">
                <div className="conversation-label"><AudioLines /> Conversation</div>
                <span className="local-tag"><Shield size={10} style={{ display: 'inline', verticalAlign: '-1px', marginRight: 4 }} />LOCAL SESSION</span>
              </div>
              <div className="transcript" aria-live="polite" data-testid="list-transcript">
                {messages.length === 0 ? (
                  <div className="empty-welcome">
                    <div className="orb-wrap"><div className={`voice-orb ${agentState === 'LISTENING' ? 'listening' : ''}`}><AudioLines /></div></div>
                    <h2 className="empty-title">A little help, right here.</h2>
                    <p className="empty-copy">Ask me to find a file, open an application, or help with a small task. I’ll show you what I’m doing and ask before anything needs your permission.</p>
                    <button className="suggestion" type="button" onClick={() => setDraft('Find the document I was working on recently')} data-testid="button-suggestion">“Find the document I was working on recently”</button>
                  </div>
                ) : messages.map((message) => (
                  <article className={`message ${message.role}`} key={message.id} data-testid={`message-${message.role}-${message.id}`}>
                    <div className="message-avatar">{message.role === 'assistant' ? <AudioLines /> : <UserRound />}</div>
                    <div className="message-body">
                      <div className="message-who">{message.role === 'assistant' ? 'AV Assistant' : 'You'}</div>
                      <div className="message-text">{message.content}</div>
                      {message.role === 'assistant' && message.id === messages.filter((item) => item.role === 'assistant').at(-1)?.id && (
                        <button type="button" className="suggestion" style={{ marginTop: 9 }} onClick={() => void speakResponse(message.content)} disabled={audioBusy} data-testid={`button-replay-${message.id}`}>
                          <Headphones size={12} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 5 }} />Play response
                        </button>
                      )}
                    </div>
                  </article>
                ))}
                {isBusy && agentState !== 'WAITING_FOR_PERMISSION' && (
                  <div className="busy-line" data-testid="status-agent-working"><span className="busy-dots"><i /><i /><i /></span>{statusCopy[agentState]}</div>
                )}
                {agentState === 'SPEAKING' && <div className="busy-line" data-testid="status-speaking"><AudioLines size={13} /> Speaking response</div>}
                <div style={{ height: 1 }} />
              </div>
              <div className="composer-wrap">
                {reviewText !== null && (
                  <div className="review-box" data-testid="panel-transcript-review">
                    <div className="review-label"><span>Review recognized words</span><button type="button" onClick={() => setReviewText(null)} aria-label="Discard transcript" style={{ border: 0, color: '#899187', background: 'transparent' }}><X size={13} /></button></div>
                    <textarea className="review-input" aria-label="Edit recognized words" value={reviewText} onChange={(event) => setReviewText(event.target.value)} data-testid="input-transcript-review" />
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 7 }}>
                      <button className="decision deny" type="button" style={{ height: 29 }} onClick={() => setReviewText(null)} data-testid="button-discard-transcript">Discard</button>
                      <button className="decision allow" type="button" style={{ height: 29, padding: '0 12px' }} onClick={() => void submitMessage(reviewText)} disabled={!reviewText.trim() || !health?.online} data-testid="button-send-transcript">Send request</button>
                    </div>
                  </div>
                )}
                <form className="composer" onSubmit={(event) => { event.preventDefault(); void submitMessage(draft); }}>
                  <textarea className="composer-input" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submitMessage(draft); }
                  }} placeholder="Write a request for your assistant…" rows={1} aria-label="Write a request" data-testid="input-message" />
                  <button type="button" className={`mic-button ${agentState === 'LISTENING' ? 'active' : ''}`} onClick={agentState === 'LISTENING' ? stopRecording : () => void startRecording()} aria-label={agentState === 'LISTENING' ? 'Stop recording' : 'Start voice recording'} title={agentState === 'LISTENING' ? 'Stop recording' : 'Record a voice request'} disabled={isBusy && agentState !== 'LISTENING'} data-testid="button-microphone">
                    {agentState === 'LISTENING' ? <MicOff /> : <Mic />}
                  </button>
                  <button className="send-button" type="submit" aria-label="Send request" disabled={!draft.trim() || !health?.online || isBusy} data-testid="button-send"><Send /></button>
                </form>
                <div className="composer-hint"><span>Enter to send · Shift + Enter for a new line</span><span>{agentState === 'LISTENING' ? 'Tap the microphone to finish' : 'Speech uses your configured provider'}</span></div>
              </div>
            </section>

            <aside className="side-stack" aria-label="Assistant activity and permissions">
              {pending && (
                <section className="permission-card" aria-labelledby="permission-title" data-testid="panel-permission">
                  <div className="permission-top"><div className="permission-symbol"><Shield /></div><div><h2 className="permission-title" id="permission-title">{pending.title}</h2><div className="permission-details">{pending.details}</div></div></div>
                  <div className="permission-actions">
                    <button className="decision deny" type="button" onClick={() => void decidePermission(false)} data-testid="button-deny">DENY</button>
                    <button className="decision allow" type="button" onClick={() => void decidePermission(true)} data-testid="button-allow">ALLOW</button>
                  </div>
                </section>
              )}
              <section className="side-card">
                <div className="side-card-head"><div className="side-card-title"><Activity />Tool activity</div><span className="count-label">{activities.length ? `${activities.length} logged` : 'LIVE'}</span></div>
                {activities.length === 0 ? <div className="activity-empty" data-testid="empty-tool-activity">No local tools have been used in this session. When a task needs one, its activity will appear here.</div> : (
                  <div className="activity-list" data-testid="list-tool-activity">
                    {activities.slice(-8).reverse().map((item) => (
                      <div className="activity-item" key={item.id} data-testid={`activity-${item.id}`}>
                        <div className="activity-icon"><Terminal /></div>
                        <div className="activity-text"><div className="activity-name">{item.name}</div><div className={`activity-status ${/denied|fail|error/i.test(item.status) ? 'failed' : /complete|success|done/i.test(item.status) ? 'done' : ''}`}>{item.status}</div>{item.result && <div className="activity-result">{item.result}</div>}</div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="side-card">
                <div className="side-card-head"><div className="side-card-title"><LockKeyhole />Local permissions</div><button className="icon-button" style={{ width: 27, height: 27, border: 0, background: 'transparent' }} type="button" aria-label="Edit permissions" onClick={openSettings} data-testid="button-edit-permissions"><Settings2 size={14} /></button></div>
                <div className="permissions-summary">
                  <div className="perm-line"><span><Folder size={12} style={{ display: 'inline', marginRight: 6, verticalAlign: '-2px' }} />Allowed folders</span><span className="perm-value">{settings?.allowed_directories.length ?? '—'}</span></div>
                  <div className="perm-line"><span><Terminal size={12} style={{ display: 'inline', marginRight: 6, verticalAlign: '-2px' }} />Allowed apps</span><span className="perm-value">{settings?.allowed_applications.length ?? '—'}</span></div>
                </div>
                <div className="provider-state"><span className={`provider-dot ${providerReady ? '' : 'off'}`} />{providerReady ? `${health?.providerName || settings?.provider_name || 'AI provider'} configured` : health?.online ? `${health?.providerName || settings?.provider_name || 'AI provider'} needs setup` : 'Waiting for companion'}</div>
              </section>

              <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#909187', fontSize: 10, padding: '0 3px' }}>
                <CircleHelp size={13} /> Only your local companion can act on your computer.
              </div>
            </aside>
          </div>
        </div>
      </main>

      {isSettingsOpen && (
        <div className="settings-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}>
          <section className="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title" data-testid="panel-settings">
            <div className="settings-head">
              <div><h2 id="settings-title">Permissions & settings</h2><p>Choose what your local companion is allowed to access. These controls are enforced on your computer.</p></div>
              <button className="icon-button" type="button" aria-label="Close settings" onClick={() => setSettingsOpen(false)} data-testid="button-close-settings"><X /></button>
            </div>
            {!health?.online && <div className="status-banner" style={{ marginTop: 17, marginBottom: 0 }} role="alert"><AlertCircle /><span>The local companion is offline. Settings cannot be loaded or changed.</span></div>}
            {settingsLoading && <div className="settings-section" aria-live="polite"><h3>Loading local settings</h3><div className="activity-empty">Contacting the companion on this device…</div></div>}
            {settingsError && <div className="status-banner" role="alert" style={{ marginTop: 17 }}><AlertCircle /><span>{settingsError}</span><button type="button" onClick={() => void loadSettings()}>Retry</button></div>}
            {settings && !settingsLoading && (
              <>
                <div className="settings-section">
                  <h3>Allowed directories</h3>
                  <div className="settings-list">
                    {settings.allowed_directories.map((directory) => <span className="setting-chip" key={directory}><Folder size={11} />{directory}<button type="button" aria-label={`Remove ${directory}`} onClick={() => setSettings((current) => current ? { ...current, allowed_directories: current.allowed_directories.filter((value) => value !== directory) } : current)} data-testid={`button-remove-directory-${directory}`}><X /></button></span>)}
                    {!settings.allowed_directories.length && <span style={{ color: '#92958a', fontSize: 11 }}>No directories are currently allowed.</span>}
                  </div>
                  <form className="add-setting" onSubmit={(event) => { event.preventDefault(); const value = newDirectory.trim(); if (!value || settings.allowed_directories.includes(value)) return; setSettings({ ...settings, allowed_directories: [...settings.allowed_directories, value] }); setNewDirectory(''); }}>
                    <input value={newDirectory} onChange={(event) => setNewDirectory(event.target.value)} placeholder="Add a local folder path" aria-label="Add allowed directory" data-testid="input-add-directory" />
                    <button type="submit" disabled={!newDirectory.trim()} data-testid="button-add-directory"><Plus size={13} style={{ verticalAlign: '-2px' }} /> Add</button>
                  </form>
                </div>
                <div className="settings-section">
                  <h3>Allowed applications</h3>
                  <div className="settings-list">
                    {settings.allowed_applications.map((application) => <span className="setting-chip" key={application}><Terminal size={11} />{application}<button type="button" aria-label={`Remove ${application}`} onClick={() => setSettings((current) => current ? { ...current, allowed_applications: current.allowed_applications.filter((value) => value !== application) } : current)} data-testid={`button-remove-application-${application}`}><X /></button></span>)}
                    {!settings.allowed_applications.length && <span style={{ color: '#92958a', fontSize: 11 }}>No applications are currently allowed.</span>}
                  </div>
                  <form className="add-setting" onSubmit={(event) => { event.preventDefault(); const value = newApplication.trim(); if (!value || settings.allowed_applications.includes(value)) return; setSettings({ ...settings, allowed_applications: [...settings.allowed_applications, value] }); setNewApplication(''); }}>
                    <input value={newApplication} onChange={(event) => setNewApplication(event.target.value)} placeholder="Add an application name" aria-label="Add allowed application" data-testid="input-add-application" />
                    <button type="submit" disabled={!newApplication.trim()} data-testid="button-add-application"><Plus size={13} style={{ verticalAlign: '-2px' }} /> Add</button>
                  </form>
                </div>
                <div className="settings-section">
                  <h3>Provider</h3>
                  <div className="settings-item"><span>AI service readiness<small>Reported by the local companion</small></span><span className="perm-value">{providerReady ? 'READY' : 'NOT REPORTED'}</span></div>
                  {health?.providerName && <div className="settings-item"><span>Provider</span><span className="perm-value">{health.providerName}</span></div>}
                </div>
                <div className="settings-note"><Shield size={12} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 5 }} />Changing this list does not grant access from this page. Your local companion validates permissions and performs every tool action.</div>
                <button className="save-settings" type="button" onClick={() => void saveSettings()} disabled={settingsSaving || !health?.online} data-testid="button-save-settings">{settingsSaving ? 'Saving locally…' : 'Save permissions on this device'}</button>
                {settingsError && <div className="error-inline" role="alert">{settingsError}</div>}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function Router() {
  return <Switch><Route path="/" component={App} /><Route component={NotFound} /></Switch>;
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function RootApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <RoutedErrorBoundary><Router /></RoutedErrorBoundary>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default RootApp;