import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { WebSocketServer } from 'ws';
import { SessionHistory } from './session-history.js';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

function sendJSON(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, { 'Content-Type': 'application/json', ...CORS_HEADERS });
  res.end(body);
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => (body += chunk));
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}); } catch { reject(new Error('Invalid JSON')); }
    });
    req.on('error', reject);
  });
}

const MIME_TYPES = {
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.ts': 'application/typescript',
  '.json': 'application/json',
  '.csv': 'text/csv',
  '.xml': 'application/xml',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.zip': 'application/zip',
  '.py': 'text/x-python',
  '.sh': 'application/x-sh',
};

export class ManusClawHttpServer {
  constructor({ port, host, logger, gatewayBridge, workspaceDir, openclawHome, agentId }) {
    this.port = port || 18788;
    this.host = host || '0.0.0.0';
    this.logger = logger;
    this.gatewayBridge = gatewayBridge;
    this.workspaceDir = workspaceDir || '/home/node/.openclaw/workspace';
    this.server = null;
    this.sessionHistory = new SessionHistory({
      openclawHome: openclawHome || '/home/node/.openclaw',
      agentId: agentId || 'main',
      logger,
    });
  }

  start() {
    this.server = http.createServer((req, res) => this._handleRequest(req, res));

    // Operator Terminal WS: ws://host:port/terminal/{sessionId}, sessionId
    // coming from a prior POST /terminal/open response.
    this.terminalWss = new WebSocketServer({ noServer: true });
    this.server.on('upgrade', (req, socket, head) => {
      const url = new URL(req.url, `http://${req.headers.host}`);
      const match = url.pathname.match(/^\/terminal\/([^/]+)$/);
      if (!match) {
        socket.destroy();
        return;
      }
      const sessionId = decodeURIComponent(match[1]);
      this.terminalWss.handleUpgrade(req, socket, head, (ws) => {
        this._handleTerminalSocket(ws, sessionId);
      });
    });

    this.server.listen(this.port, this.host, () => {
      this.logger?.info?.(`[manus-claw] HTTP server listening on ${this.host}:${this.port}`);
    });
    this.server.on('error', (err) => {
      this.logger?.error?.(`[manus-claw] HTTP server error: ${String(err)}`);
    });
  }

  stop() {
    if (this.terminalWss) {
      this.terminalWss.close();
      this.terminalWss = null;
    }
    if (this.server) {
      this.server.close();
      this.server = null;
    }
  }

  async _handleRequest(req, res) {
    // Handle CORS preflight
    if (req.method === 'OPTIONS') {
      res.writeHead(204, CORS_HEADERS);
      res.end();
      return;
    }

    const url = new URL(req.url, `http://${req.headers.host}`);

    if (url.pathname === '/health' && req.method === 'GET') {
      return sendJSON(res, 200, {
        status: 'ok',
        gateway_ready: this.gatewayBridge?.isGatewayReady?.() ?? false,
      });
    }

    if (url.pathname === '/chat' && req.method === 'POST') {
      return this._handleChat(req, res);
    }

    if (url.pathname === '/workspace' && req.method === 'POST') {
      return this._handleWorkspaceUpload(req, res, url);
    }

    if (url.pathname === '/terminal/open' && req.method === 'POST') {
      return this._handleTerminalOpen(req, res);
    }

    if (url.pathname === '/history' && req.method === 'GET') {
      return this._handleHistory(req, res, url);
    }

    if (url.pathname.startsWith('/files/') && req.method === 'GET') {
      return this._handleFileDownload(req, res, url);
    }

    sendJSON(res, 404, { error: 'Not found' });
  }

  /**
   * POST /workspace?file_id=xxx&filename=yyy
   * Accept raw file body and save to workspace/upload/{file_id}_{filename}.
   * Returns { path: "/absolute/path/to/file" }.
   * Mirrors kimi-claw's ensureKimiFileDownloaded() caching strategy:
   * if file with same file_id prefix exists and size > 0, reuse it.
   */
  async _handleWorkspaceUpload(req, res, url) {
    const fileId = url.searchParams.get('file_id');
    const rawFilename = url.searchParams.get('filename') || 'file';
    if (!fileId) {
      return sendJSON(res, 400, { error: 'file_id is required' });
    }

    const safeName = path.basename(rawFilename).replace(/[^a-zA-Z0-9._\-\u4e00-\u9fff]/g, '_');
    const uploadDir = path.join(this.workspaceDir, 'upload');

    // Ensure upload dir exists
    try { fs.mkdirSync(uploadDir, { recursive: true }); } catch {}

    // Cache check: if file with this fileId prefix already exists, reuse it
    const prefix = `${fileId}_`;
    try {
      const existing = fs.readdirSync(uploadDir).find(f => f.startsWith(prefix));
      if (existing) {
        const existingPath = path.join(uploadDir, existing);
        const stat = fs.statSync(existingPath);
        if (stat.size > 0) {
          this.logger?.info?.(`[workspace] cache hit: ${existingPath}`);
          return sendJSON(res, 200, { path: existingPath, cached: true });
        }
      }
    } catch {}

    // Read the raw body
    const chunks = [];
    for await (const chunk of req) {
      chunks.push(chunk);
    }
    const data = Buffer.concat(chunks);

    if (data.length === 0) {
      return sendJSON(res, 400, { error: 'Empty file body' });
    }

    const destPath = path.join(uploadDir, `${prefix}${safeName}`);
    try {
      fs.writeFileSync(destPath, data);
      this.logger?.info?.(`[workspace] saved ${destPath} (${data.length} bytes)`);
      return sendJSON(res, 200, { path: destPath, cached: false, size: data.length });
    } catch (err) {
      this.logger?.error?.(`[workspace] write failed: ${err}`);
      return sendJSON(res, 500, { error: `Write failed: ${err}` });
    }
  }

  /**
   * POST /terminal/open
   * Body (all optional): { cols, rows, agent_id }. cols/rows default to
   * 80x24; agent_id defaults to this plugin's configured agent.
   * Opens a real PTY session via the gateway's operator terminal.open RPC.
   * Returns { session_id, agent_id, shell, cwd, confined } on success —
   * session_id is what the client then dials into the terminal WS endpoint
   * at ws://.../terminal/{session_id}.
   */
  async _handleTerminalOpen(req, res) {
    let body;
    try {
      body = await parseBody(req);
    } catch {
      return sendJSON(res, 400, { error: 'Invalid request body' });
    }

    if (!this.gatewayBridge?.isGatewayReady?.()) {
      return sendJSON(res, 503, { error: 'Gateway not ready' });
    }

    const cols = Number.isInteger(body.cols) ? body.cols : 80;
    const rows = Number.isInteger(body.rows) ? body.rows : 24;

    try {
      const result = await this.gatewayBridge.openTerminal({
        agentId: body.agent_id,
        cols,
        rows,
      });
      return sendJSON(res, 200, {
        session_id: result.sessionId,
        agent_id: result.agentId,
        shell: result.shell,
        cwd: result.cwd,
        confined: result.confined,
      });
    } catch (err) {
      this.logger?.warn?.(`[terminal] open failed: ${err}`);
      return sendJSON(res, 502, { error: String(err?.message || err) });
    }
  }

  /**
   * WS ws://host:port/terminal/{sessionId}
   *
   * Client -> server messages (JSON text frames):
   *   {"type":"input","data":"..."}          -> terminal.input
   *   {"type":"resize","cols":N,"rows":N}    -> terminal.resize
   *
   * Server -> client messages:
   *   {"type":"data","seq":N,"data":"..."}                        (terminal.data)
   *   {"type":"exit","exit_code":N|null,"signal":N|null,"reason":"...","error"?:"..."}  (terminal.exit, then the socket is closed)
   *   {"type":"error","error":"..."}                               (bad input / RPC failure, socket stays open)
   *
   * On WS close (client navigates away, network drop, etc.) the underlying
   * PTY session is closed too via terminal.close — this endpoint does not
   * support detach/reattach in this task; every WS owns its terminal for its
   * lifetime.
   */
  _handleTerminalSocket(ws, sessionId) {
    if (!this.gatewayBridge?.isGatewayReady?.()) {
      try { ws.send(JSON.stringify({ type: 'error', error: 'Gateway not ready' })); } catch {}
      try { ws.close(1011, 'gateway not ready'); } catch {}
      return;
    }

    let closed = false;

    const cleanup = this.gatewayBridge.registerTerminalHandler(sessionId, {
      onData: (payload) => {
        if (closed || ws.readyState !== ws.OPEN) return;
        try {
          ws.send(JSON.stringify({ type: 'data', seq: payload.seq, data: payload.data }));
        } catch {}
      },
      onExit: (payload) => {
        if (closed) return;
        closed = true;
        if (ws.readyState === ws.OPEN) {
          try {
            ws.send(JSON.stringify({
              type: 'exit',
              exit_code: payload.exitCode ?? null,
              signal: payload.signal ?? null,
              reason: payload.reason,
              ...(payload.error ? { error: payload.error } : {}),
            }));
          } catch {}
        }
        try { ws.close(1000, 'terminal exit'); } catch {}
      },
    });

    ws.on('message', async (raw) => {
      if (closed) return;
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        try { ws.send(JSON.stringify({ type: 'error', error: 'Invalid JSON' })); } catch {}
        return;
      }

      try {
        if (msg.type === 'input') {
          await this.gatewayBridge.sendTerminalInput(sessionId, msg.data ?? '');
        } else if (msg.type === 'resize') {
          await this.gatewayBridge.resizeTerminal(sessionId, msg.cols, msg.rows);
        } else {
          try { ws.send(JSON.stringify({ type: 'error', error: `unknown message type: ${msg.type}` })); } catch {}
        }
      } catch (err) {
        if (ws.readyState === ws.OPEN) {
          try { ws.send(JSON.stringify({ type: 'error', error: String(err?.message || err) })); } catch {}
        }
      }
    });

    ws.on('close', () => {
      if (closed) return;
      closed = true;
      cleanup?.();
      this.gatewayBridge.closeTerminal(sessionId).catch(() => {});
    });
  }

  async _handleChat(req, res) {
    let body;
    try {
      body = await parseBody(req);
    } catch {
      return sendJSON(res, 400, { error: 'Invalid request body' });
    }

    const { message, session_id, stream = true } = body;
    if (!message) {
      return sendJSON(res, 400, { error: 'message is required' });
    }

    // Keep in sync with /history and the backend (ClawChatRequest), which
    // all default to "default" (mapped internally to "manus:default").
    const sessionId = session_id || 'default';

    if (!this.gatewayBridge?.isGatewayReady?.()) {
      return sendJSON(res, 503, { error: 'Gateway not ready' });
    }

    if (stream) {
      // SSE streaming response
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        ...CORS_HEADERS,
      });

      const requestId = randomUUID();
      let done = false;

      const cleanup = this.gatewayBridge.registerResponseHandler(requestId, sessionId, {
        onChunk: (text) => {
          if (done) return;
          const data = JSON.stringify({ type: 'text', content: text });
          res.write(`event: chunk\ndata: ${data}\n\n`);
        },
        onFile: (fileInfo) => {
          if (done) return;
          // fileInfo is a FileInfo object: { file_id, filename, content_type, size, upload_date, file_url }
          const data = JSON.stringify({ type: 'file', ...fileInfo });
          res.write(`event: file\ndata: ${data}\n\n`);
        },
        onTool: (toolData) => {
          if (done) return;
          // toolData is the gateway's raw payload.data for stream:"tool":
          // { phase: 'start'|'update'|'result', name, toolCallId,
          //   args? (start), partialResult? (update), result? (result),
          //   isError? (result), meta? } — passed through as-is, see
          // gateway-bridge.js's onTool doc comment for the full field list.
          const data = JSON.stringify({ type: 'tool', ...toolData });
          res.write(`event: tool\ndata: ${data}\n\n`);
        },
        onComplete: (stopReason) => {
          if (done) return;
          done = true;
          const data = JSON.stringify({ type: 'done', stop_reason: stopReason });
          res.write(`event: done\ndata: ${data}\n\n`);
          res.end();
          cleanup?.();
        },
        onError: (errMsg) => {
          if (done) return;
          done = true;
          const data = JSON.stringify({ type: 'error', error: errMsg });
          res.write(`event: error\ndata: ${data}\n\n`);
          res.end();
          cleanup?.();
        },
      });

      req.on('close', () => {
        if (!done) {
          done = true;
          cleanup?.();
        }
      });

      try {
        await this.gatewayBridge.sendPrompt(sessionId, message, requestId);
      } catch (err) {
        if (!done) {
          done = true;
          const data = JSON.stringify({ type: 'error', error: String(err) });
          res.write(`event: error\ndata: ${data}\n\n`);
          res.end();
          cleanup?.();
        }
      }
    } else {
      // Non-streaming: collect all chunks then respond
      try {
        const result = await this.gatewayBridge.sendPromptSync(sessionId, message);
        sendJSON(res, 200, { content: result.content, stop_reason: result.stopReason });
      } catch (err) {
        sendJSON(res, 500, { error: String(err) });
      }
    }
  }

  /**
   * GET /history?session_id=xxx&limit=200
   *
   * Strategy (mirrors kimi-claw):
   *   1. Read local .jsonl session file (primary source)
   *   2. Fetch from gateway via chat.history (complement)
   *   3. Merge & deduplicate, return unified list in chronological order
   */
  async _handleHistory(req, res, url) {
    const rawSessionId = url.searchParams.get('session_id') || 'default';
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '200', 10), 500);

    // Map to the sessionKey format OpenClaw uses internally: "manus:{rawSessionId}"
    const sessionId = `manus:${rawSessionId}`;

    // 1. Local first: read from .jsonl
    const localEntries = this.sessionHistory.readEntries(sessionId, limit);
    this.logger?.info?.(`[history] local entries: ${localEntries.length} for session=${sessionId}`);

    // 2. Gateway complement (uses the raw sessionId for gateway bridge)
    let gwEntries = [];
    try {
      gwEntries = await this.gatewayBridge.fetchGatewayHistory(rawSessionId, limit);
      this.logger?.info?.(`[history] gateway entries: ${gwEntries.length}`);
    } catch (err) {
      this.logger?.warn?.(`[history] gateway fetch failed: ${err}`);
    }

    // 3. Merge & deduplicate
    const merged = this._mergeAndDedup(localEntries, gwEntries, limit);

    // 4. Normalize content & extract attachments
    const messages = merged.map(e => {
      let content = e.content;
      const attachments = [];

      if (Array.isArray(content)) {
        const textParts = [];
        for (const block of content) {
          if (!block || typeof block !== 'object') continue;
          const btype = block.type;
          if (btype === 'text') {
            textParts.push(block.text || '');
          } else if (btype === 'resource_link') {
            const uri = block.uri;
            if (uri) {
              const m = uri.match(/^manus-file:\/\/(.+)$/);
              attachments.push({
                file_id: m ? m[1] : undefined,
                uri,
                filename: block.name || block.title || (m ? m[1] : undefined),
                content_type: block.mimeType || block.mime_type || undefined,
              });
            }
          } else if (btype === 'file' || btype === 'image') {
            attachments.push({
              uri: block.uri || undefined,
              filename: block.fileName || block.file_name || block.filename || block.name || undefined,
              content_type: block.mimeType || block.mime_type || undefined,
            });
          } else if (btype === 'resource' && block.resource) {
            const r = block.resource;
            attachments.push({
              uri: r.uri || block.uri || undefined,
              filename: r.fileName || r.file_name || r.filename || r.name || undefined,
              content_type: r.mimeType || r.mime_type || undefined,
            });
          }
        }
        content = textParts.join('');
      } else if (content && typeof content === 'object') {
        content = content.text || JSON.stringify(content);
      }

      // Extract <MANUS_FILE .../> tags from text content
      if (typeof content === 'string' && content.includes('<MANUS_FILE')) {
        const tagRegex = /<MANUS_FILE\b([^>]*)\/>/g;
        let match;
        while ((match = tagRegex.exec(content)) !== null) {
          const attrs = match[1];
          const id = attrs.match(/\bid\s*=\s*"([^"]+)"/)?.[1];
          const name = attrs.match(/\bname\s*=\s*"([^"]+)"/)?.[1];
          const type = attrs.match(/\btype\s*=\s*"([^"]+)"/)?.[1];
          const size = attrs.match(/\bsize\s*=\s*"([^"]+)"/)?.[1];
          if (id) {
            attachments.push({
              file_id: id,
              filename: name || id,
              content_type: type || undefined,
              size: size ? parseInt(size, 10) : undefined,
            });
          }
        }
        content = content.replace(/<MANUS_FILE\b[^>]*\/>/g, '').trim();
      }

      const msg = {
        role: e.role,
        content: typeof content === 'string' ? content : '',
        timestamp: e.timestamp || 0,
        toolCallId: e.toolCallId,
        toolName: e.toolName,
        stopReason: e.stopReason,
      };
      if (attachments.length) msg.attachments = attachments;
      return msg;
    });

    sendJSON(res, 200, { messages });
  }

  /**
   * Merge local and gateway entries, dedup by content signature.
   * Local entries take priority; gateway entries fill gaps.
   */
  _mergeAndDedup(local, gateway, limit) {
    const dedupKey = (entry) => {
      let text = '';
      if (typeof entry.content === 'string') {
        text = entry.content;
      } else if (Array.isArray(entry.content)) {
        text = entry.content.filter(c => c?.type === 'text').map(c => c.text || '').join('');
      }
      return `${entry.role}:${text.slice(0, 200)}`;
    };

    // Local entries are authoritative — keep all of them (no internal dedup).
    // Build a bag (counter) from local entries so that each local entry
    // "consumes" one matching gateway entry, preventing cross-source dupes
    // while preserving intentional repeats within a single source.
    const localBag = new Map();
    const result = [...local];

    for (const e of local) {
      const key = dedupKey(e);
      localBag.set(key, (localBag.get(key) || 0) + 1);
    }
    for (const e of gateway) {
      const key = dedupKey(e);
      const remaining = localBag.get(key) || 0;
      if (remaining > 0) {
        localBag.set(key, remaining - 1);
        continue;
      }
      result.push(e);
    }

    // Sort by timestamp (chronological)
    result.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
    return result.slice(-limit);
  }

  _handleFileDownload(req, res, url) {
    // Decode the filename from URL, e.g. /files/report.pdf -> report.pdf
    const rawName = decodeURIComponent(url.pathname.slice('/files/'.length));
    // Sanitize: strip any path traversal
    const safeName = path.basename(rawName);
    if (!safeName) {
      return sendJSON(res, 400, { error: 'Invalid filename' });
    }

    const filePath = path.join(this.workspaceDir, safeName);
    // Ensure resolved path is still inside workspaceDir
    if (!filePath.startsWith(path.resolve(this.workspaceDir))) {
      return sendJSON(res, 403, { error: 'Forbidden' });
    }

    fs.stat(filePath, (statErr, stat) => {
      if (statErr || !stat.isFile()) {
        return sendJSON(res, 404, { error: 'File not found' });
      }

      const ext = path.extname(safeName).toLowerCase();
      const contentType = MIME_TYPES[ext] || 'application/octet-stream';

      res.writeHead(200, {
        'Content-Type': contentType,
        'Content-Length': stat.size,
        'Content-Disposition': `attachment; filename="${safeName}"`,
        ...CORS_HEADERS,
      });

      fs.createReadStream(filePath).pipe(res);
    });
  }
}
