import { randomUUID } from 'node:crypto';

/**
 * GatewayBridge connects to OpenClaw's local gateway and provides
 * a simple send/receive interface for the HTTP server.
 *
 * Text comes in as: event:agent, payload.stream="assistant", payload.data.delta or .text
 * Tool calls via:    event:agent, payload.stream="tool", payload.data.phase="start"|"update"|"result"
 * Run ends via:     event:agent, payload.stream="lifecycle", payload.data.phase="end"
 * Run error via:    event:agent, payload.stream="lifecycle", payload.data.phase="error"
 * Fallback end:     event:chat,  payload.state="final"
 *
 * File uploads are handled by the plugin's registerTool() API (see index.js).
 * When the agent calls manus_upload_file, OpenClaw invokes the tool's execute()
 * function directly. execute() calls bridge.notifyFileUploaded() to push a
 * file SSE event to the active frontend request.
 *
 * Operator Terminal (real PTY) events arrive as top-level gateway events, not
 * inside the agent envelope: event:'terminal.data' (payload: {sessionId, seq,
 * data}) and event:'terminal.exit' (payload: {sessionId, exitCode, signal,
 * reason, error?}). Because this plugin keeps exactly one privileged operator
 * connection to the gateway (see gateway-client.js), every terminal session
 * opened via that connection delivers its events on the same message stream,
 * disambiguated by payload.sessionId — see registerTerminalHandler().
 */
export class GatewayBridge {
  constructor({ agentId, logger }) {
    this.agentId = agentId || 'main';
    this.logger = logger;
    this.gatewayClient = null; // set by index.js after construction
    this.fileResolver = null;  // set by index.js after construction

    // Map of requestId -> handler object
    this._responseHandlers = new Map();
    // Map of gwRequestId -> requestId
    this._gwRequestMap = new Map();
    // Map of runId -> requestId
    this._runIdMap = new Map();
    // Map of terminal sessionId -> handler object ({ onData, onExit })
    this._terminalHandlers = new Map();

    this._initialized = false;
  }

  isGatewayReady() {
    return this.gatewayClient?.isReady() && this._initialized;
  }

  onGatewayReady() {
    this._initialized = true;
    this.logger?.info?.('[bridge] gateway ready');
  }

  /**
   * Called by the manus_upload_file tool execute() in index.js after a
   * successful upload. Pushes a file event to all active SSE connections.
   */
  notifyFileUploaded(fileInfo) {
    for (const handler of this._responseHandlers.values()) {
      handler.onFile?.(fileInfo);
    }
  }

  handleGatewayMessage(msg) {
    if (!msg || typeof msg !== 'object') return;

    const { type, event, id } = msg;

    if (type === 'res' && id && id !== 'connect') {
      this._handleResMessage(msg);
      return;
    }

    if (type === 'event' && event === 'agent') {
      this._handleAgentEvent(msg.payload);
      return;
    }

    if (type === 'event' && event === 'chat') {
      this._handleChatEvent(msg.payload);
      return;
    }

    if (type === 'event' && (event === 'terminal.data' || event === 'terminal.exit')) {
      this._handleTerminalEvent(event, msg.payload);
      return;
    }
  }

  _handleResMessage(msg) {
    const { id, ok, payload, error } = msg;
    const reqId = this._gwRequestMap.get(id);

    if (!ok) {
      const errMsg = (error?.message) || payload?.error || 'agent request failed';
      this.logger?.warn?.(`[bridge] agent request failed id=${id}: ${errMsg}`);
      if (reqId) {
        this._responseHandlers.get(reqId)?.onError?.(errMsg);
        this._cleanupByReqId(reqId);
      }
      return;
    }

    // Gateway res for 'agent' method: bind runId to reqId
    const runId = payload?.runId ?? payload?.run_id;
    if (runId && reqId) {
      this._runIdMap.set(runId, reqId);
      this.logger?.info?.(`[bridge] agent accepted runId=${runId}`);
    }
  }

  _handleAgentEvent(payload) {
    if (!payload) return;

    const stream = payload.stream;
    const data = payload.data || {};
    const runId = payload.runId ?? payload.run_id;
    if (!runId) return;

    const reqId = this._runIdMap.get(runId);
    const handler = reqId ? this._responseHandlers.get(reqId) : null;
    if (!handler) return;

    if (stream === 'assistant') {
      handler._hasAssistantStream = true;
      const text = _extractText(data.delta) ?? _extractText(data.text);
      if (text) {
        handler.onChunk?.(_sanitizeSandboxLinks(text));
        return;
      }
      if (Array.isArray(data.content)) {
        for (const block of data.content) {
          if (block?.type === 'text' && typeof block.text === 'string' && block.text) {
            handler.onChunk?.(_sanitizeSandboxLinks(block.text));
            break;
          }
        }
      }
      return;
    }

    if (stream === 'tool') {
      // data: { phase: 'start'|'update'|'result', name, toolCallId,
      //         args? (start), partialResult? (update), result? (result),
      //         isError? (result), meta? }. Forwarded as-is to the HTTP
      //         layer's SSE writer — see http-server.js's onTool handler.
      handler.onTool?.(data);
      return;
    }

    if (stream === 'lifecycle') {
      const phase = data.phase;
      if (phase === 'end') {
        this.logger?.info?.(`[bridge] agent lifecycle end runId=${runId}`);
        handler.onComplete?.('end_turn');
        this._cleanupByReqId(reqId);
        return;
      }
      if (phase === 'cancelled' || phase === 'cancel') {
        this.logger?.info?.(`[bridge] agent lifecycle cancelled runId=${runId}`);
        handler.onComplete?.('cancelled');
        this._cleanupByReqId(reqId);
        return;
      }
      if (phase === 'error') {
        const errMsg = data.error?.message ?? data.message ?? 'agent lifecycle error';
        this.logger?.warn?.(`[bridge] agent lifecycle error runId=${runId}: ${errMsg}`);
        handler.onError?.(errMsg);
        this._cleanupByReqId(reqId);
        return;
      }
    }
  }

  _handleChatEvent(payload) {
    if (!payload) return;

    const { runId, run_id, state, message } = payload;
    const actualRunId = runId ?? run_id;

    // Fallback text delivery from chat event (only if we never got assistant stream)
    if (message?.role === 'assistant') {
      const reqId = actualRunId ? this._runIdMap.get(actualRunId) : null;
      const handler = reqId ? this._responseHandlers.get(reqId) : null;
      if (handler && !handler._hasAssistantStream) {
        const content = message.content;
        let text = '';
        if (Array.isArray(content)) {
          text = content.filter(c => c?.type === 'text').map(c => c.text || '').join('');
        } else if (typeof content === 'string') {
          text = content;
        }
        if (text) handler.onChunk?.(_sanitizeSandboxLinks(text));
      }
    }

    // State-based completion fallback
    const lstate = typeof state === 'string' ? state.toLowerCase() : '';
    if (lstate === 'final') {
      const reqId = actualRunId ? this._runIdMap.get(actualRunId) : null;
      const handler = reqId ? this._responseHandlers.get(reqId) : null;
      if (handler) {
        this.logger?.info?.(`[bridge] chat state=final runId=${actualRunId} -> completing`);
        handler.onComplete?.('end_turn');
        this._cleanupByReqId(reqId);
      }
    }
  }

  /**
   * Dispatch a terminal.data/terminal.exit gateway event to whichever
   * terminal WS connection registered for that sessionId (see
   * registerTerminalHandler(), called from http-server.js's terminal WS
   * upgrade handler).
   */
  _handleTerminalEvent(event, payload) {
    if (!payload || !payload.sessionId) return;
    const handler = this._terminalHandlers.get(payload.sessionId);
    if (!handler) return;

    if (event === 'terminal.data') {
      handler.onData?.(payload);
      return;
    }

    if (event === 'terminal.exit') {
      this.logger?.info?.(`[bridge] terminal exit sessionId=${payload.sessionId} reason=${payload.reason}`);
      handler.onExit?.(payload);
      this._terminalHandlers.delete(payload.sessionId);
    }
  }

  registerTerminalHandler(sessionId, handlers) {
    this._terminalHandlers.set(sessionId, handlers);
    return () => this._terminalHandlers.delete(sessionId);
  }

  /**
   * Opens a new Operator Terminal (real PTY) session via the gateway's
   * terminal.open RPC, scoped to this plugin's agent by default.
   * Returns { sessionId, agentId, shell, cwd, confined }.
   */
  async openTerminal({ agentId, cols, rows } = {}) {
    if (!this.isGatewayReady()) throw new Error('Gateway not ready');
    return this.gatewayClient.request('terminal.open', {
      agentId: agentId || this.agentId,
      cols: cols || 80,
      rows: rows || 24,
    }, 15000);
  }

  async sendTerminalInput(sessionId, data) {
    if (!this.isGatewayReady()) throw new Error('Gateway not ready');
    return this.gatewayClient.request('terminal.input', { sessionId, data }, 10000);
  }

  async resizeTerminal(sessionId, cols, rows) {
    if (!this.isGatewayReady()) throw new Error('Gateway not ready');
    return this.gatewayClient.request('terminal.resize', { sessionId, cols, rows }, 10000);
  }

  async closeTerminal(sessionId) {
    if (!this.isGatewayReady()) throw new Error('Gateway not ready');
    return this.gatewayClient.request('terminal.close', { sessionId }, 10000);
  }

  _cleanupByReqId(requestId) {
    this._responseHandlers.delete(requestId);
    for (const [gwId, rId] of this._gwRequestMap.entries()) {
      if (rId === requestId) this._gwRequestMap.delete(gwId);
    }
    for (const [runId, rId] of this._runIdMap.entries()) {
      if (rId === requestId) this._runIdMap.delete(runId);
    }
  }

  registerResponseHandler(requestId, sessionId, handlers) {
    this._responseHandlers.set(requestId, { ...handlers, sessionId });
    return () => this._cleanupByReqId(requestId);
  }

  async sendPrompt(sessionId, message, requestId) {
    // Pre-process: resolve manus-file:// URIs → <MANUS_FILE /> tags
    let resolvedMessage = message;
    if (this.fileResolver && typeof message === 'string' && message.includes('manus-file://')) {
      try {
        resolvedMessage = await this.fileResolver.resolvePrompt(message);
      } catch (err) {
        this.logger?.warn?.(`[bridge] file resolution failed, using original message: ${err}`);
      }
    }

    const sessionKey = `manus:${sessionId}`;
    const gwRequestId = `gw_${randomUUID().replace(/-/g, '')}`;
    this._gwRequestMap.set(gwRequestId, requestId);

    const sent = this.gatewayClient.send({
      type: 'req',
      id: gwRequestId,
      method: 'agent',
      params: {
        agentId: this.agentId,
        sessionKey,
        message: resolvedMessage,
        idempotencyKey: `manus_${sessionId}_${Date.now()}`,
      }
    });

    if (!sent) throw new Error('Failed to send prompt to gateway');
    this.logger?.info?.(`[bridge] sent prompt gwRequestId=${gwRequestId} sessionId=${sessionId}`);
  }

  sendPromptSync(sessionId, message) {
    return new Promise((resolve, reject) => {
      const requestId = randomUUID();
      let content = '';

      const cleanup = this.registerResponseHandler(requestId, sessionId, {
        onChunk: (text) => { content += text; },
        onComplete: (stopReason) => { cleanup(); resolve({ content, stopReason }); },
        onError: (errMsg) => { cleanup(); reject(new Error(errMsg)); },
      });

      this.sendPrompt(sessionId, message, requestId).catch(err => {
        cleanup();
        reject(err);
      });
    });
  }

  /**
   * Fetch conversation history from the gateway via chat.history protocol.
   * Returns a Promise<Array> of message objects (same shape as .jsonl entries).
   */
  async fetchGatewayHistory(sessionId, limit = 100) {
    if (!this.isGatewayReady()) return [];

    const sessionKey = `manus:${sessionId}`;
    try {
      const result = await this.gatewayClient.request('chat.history', {
        sessionKey,
        limit,
      }, 15000);

      const messages = result?.messages ?? result?.payload?.messages ?? [];
      return messages
        .filter(m => m && (m.role === 'user' || m.role === 'assistant' || m.role === 'toolResult'))
        .map(m => ({
          role: m.role,
          content: m.content,
          toolCallId: m.toolCallId || m.tool_call_id || undefined,
          toolName: m.toolName || m.tool_name || undefined,
          stopReason: m.stopReason || m.stop_reason || undefined,
          timestamp: m.timestamp || undefined,
        }));
    } catch (err) {
      this.logger?.warn?.(`[bridge] chat.history request failed: ${err}`);
      return [];
    }
  }

  handleGatewayDisconnected() {
    this._initialized = false;
    for (const reqId of [...this._responseHandlers.keys()]) {
      this._responseHandlers.get(reqId)?.onError?.('Gateway disconnected');
      this._cleanupByReqId(reqId);
    }
    for (const [sessionId, handler] of [...this._terminalHandlers.entries()]) {
      handler.onExit?.({ sessionId, exitCode: null, signal: null, reason: 'disconnected' });
      this._terminalHandlers.delete(sessionId);
    }
  }
}

/**
 * Extract a plain string from various text chunk formats:
 *   "hello"  ->  "hello"
 *   {type:"text", text:"hello"}  ->  "hello"
 *   {text:"hello"}  ->  "hello"
 */
function _extractText(v) {
  if (typeof v === 'string' && v) return v;
  if (v && typeof v === 'object') {
    if (typeof v.text === 'string' && v.text) return v.text;
  }
  return null;
}

/**
 * Clean up file URLs in markdown links:
 * 1. sandbox:/api/v1/files/xxx  ->  /api/v1/files/xxx
 * 2. https://any.domain/api/v1/files/xxx  ->  /api/v1/files/xxx
 */
function _sanitizeSandboxLinks(text) {
  if (typeof text !== 'string') return text;
  return text
    .replace(/\(sandbox:(\/api\/v1\/files\/[^)]*)\)/g, '($1)')
    .replace(/\(https?:\/\/[^/)]+(\/api\/v1\/files\/[^)]*)\)/g, '($1)');
}
