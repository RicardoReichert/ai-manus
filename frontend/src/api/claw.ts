import { apiClient, ApiResponse, BASE_URL } from './client';

export type ClawStatus = 'creating' | 'running' | 'stopped' | 'error';

export interface ClawSession {
  id: string;
  user_id: string;
  name?: string | null;
  model_id: string;
  status: ClawStatus;
  container_name?: string;
  error_message?: string;
  expires_at?: string | null;
  created_at: string;
  updated_at: string;
  last_active_at: string;
}

export interface ClawEvent {
  type: 'text' | 'done' | 'error' | 'file' | 'catchup' | 'heartbeat' | 'status';
  content?: string;
  stop_reason?: string;
  error?: string;
  status?: ClawStatus;
  file_id?: string;
  filename?: string;
  content_type?: string;
  size?: number;
  upload_date?: string;
  file_url?: string;
}

export interface ClawChatAttachment {
  file_id: string;
  filename: string;
  content_type?: string;
  size: number;
  file_url?: string;
}

export interface ClawChatMessage {
  role: 'user' | 'assistant' | 'attachments';
  content: string;
  timestamp: number;
  attachments?: ClawChatAttachment[];
}

// ---- REST endpoints ----
// A user may have several sessions now — each pinned to a model chosen at
// creation, each backed by its own persistent volume so restarting its
// container (e.g. to switch models) never loses OpenClaw's native memory.

export async function listClawSessions(): Promise<ClawSession[]> {
  const response = await apiClient.get<ApiResponse<{ sessions: ClawSession[] }>>('/claw/sessions');
  return response.data.data.sessions;
}

export async function createClawSession(modelId: string, name?: string): Promise<ClawSession> {
  const response = await apiClient.post<ApiResponse<ClawSession>>('/claw/sessions', {
    model_id: modelId,
    name,
  });
  return response.data.data;
}

export async function getClawSession(sessionId: string): Promise<ClawSession> {
  const response = await apiClient.get<ApiResponse<ClawSession>>(`/claw/sessions/${sessionId}`);
  return response.data.data;
}

/**
 * Kill the session's current container and start a fresh one on the chosen
 * model — the only way to change a session's model. The session's volume is
 * untouched, so OpenClaw's native memory for it survives the restart.
 */
export async function restartClawSession(sessionId: string, modelId: string): Promise<ClawSession> {
  const response = await apiClient.post<ApiResponse<ClawSession>>(`/claw/sessions/${sessionId}/restart`, {
    model_id: modelId,
  });
  return response.data.data;
}

/** Deletes the session's record, container, AND its volume — the only
 * operation that actually discards a session's memory for good. */
export async function deleteClawSession(sessionId: string): Promise<void> {
  await apiClient.delete<ApiResponse<Record<string, never>>>(`/claw/sessions/${sessionId}`);
}

export async function getClawSessionHistory(sessionId: string): Promise<ClawChatMessage[]> {
  const response = await apiClient.get<ApiResponse<{ messages: ClawChatMessage[] }>>(`/claw/sessions/${sessionId}/history`);
  return response.data.data.messages;
}

// ---- WebSocket connection ----

export interface ClawWSCallbacks {
  onEvent: (event: ClawEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

/**
 * Manages a persistent WebSocket connection to one Claw session.
 * Auto-reconnects on disconnect with exponential backoff. Scoped to a single
 * session for its whole lifetime — switching sessions means creating a new
 * ClawWebSocket, not reusing this one.
 */
export class ClawWebSocket {
  private ws: WebSocket | null = null;
  private callbacks: ClawWSCallbacks;
  private closed = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private sessionId: string;

  constructor(sessionId: string, callbacks: ClawWSCallbacks) {
    this.sessionId = sessionId;
    this.callbacks = callbacks;
    this.connect();
  }

  private connect() {
    if (this.closed) return;

    // Same Cookie / Bearer resolve as /ws/sessions and /ws/chat. No ?token=.
    const wsBase = BASE_URL.replace(/^http/, 'ws');
    const url = `${wsBase}/ws/claw/${this.sessionId}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.callbacks.onOpen?.();
    };

    this.ws.onmessage = (e) => {
      try {
        const data: ClawEvent = JSON.parse(e.data);
        if (data.type !== 'heartbeat') {
          this.callbacks.onEvent(data);
        }
      } catch {
        // ignore
      }
    };

    this.ws.onclose = () => {
      this.callbacks.onClose?.();
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private scheduleReconnect() {
    if (this.closed) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
      this.connect();
    }, this.reconnectDelay);
  }

  /**
   * Send a chat message through the WebSocket, optionally with file attachments.
   */
  send(message: string, fileIds?: string[]) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const payload: Record<string, unknown> = { type: 'chat', message };
      if (fileIds && fileIds.length > 0) {
        payload.file_ids = fileIds;
      }
      this.ws.send(JSON.stringify(payload));
    }
  }

  /**
   * Close the connection permanently (no auto-reconnect).
   */
  disconnect() {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
