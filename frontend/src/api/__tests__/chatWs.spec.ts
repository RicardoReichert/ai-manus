import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { BASE_URL } from '../client';

/**
 * Minimal fake WebSocket implementing just enough of the browser API
 * surface that chatWs.ts touches: readyState, on{open,message,close,error},
 * send(), close(). Plus test helpers open()/receive() to drive it manually.
 */
class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) { FakeWebSocket.instances.push(this); }
  static instances: FakeWebSocket[] = [];
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = FakeWebSocket.CLOSED; this.onclose?.(); }
  /** test helper, not part of the real WebSocket API */
  open() { this.readyState = FakeWebSocket.OPEN; this.onopen?.(); }
  /** test helper */
  receive(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }); }
}

/** Parse the last frame sent on a fake socket. */
function lastSent(ws: FakeWebSocket): any {
  return JSON.parse(ws.sent[ws.sent.length - 1]);
}

/**
 * Flush pending microtasks so promise continuations (post-`await waitReady()`,
 * chained through nested async calls like chat() -> joinSession() -> request())
 * run. Several awaits may be chained, so flush a generous number of ticks.
 */
async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) {
    await Promise.resolve();
  }
}

describe('chatWs', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', FakeWebSocket);
    FakeWebSocket.instances = [];
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('constructs exactly one FakeWebSocket at the expected URL, and getChatWebSocket() is a singleton', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');

    const ws1 = getChatWebSocket();
    expect(FakeWebSocket.instances.length).toBe(1);
    const expectedUrl = `${BASE_URL.replace(/^http/, 'ws')}/ws/chat`;
    expect(FakeWebSocket.instances[0].url).toBe(expectedUrl);

    const ws2 = getChatWebSocket();
    expect(ws2).toBe(ws1);
    expect(FakeWebSocket.instances.length).toBe(1);
  });

  it('joinSession sends a well-formed join_session envelope and resolves on joined', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const joinPromise = ws.joinSession('s1');
    sock.open();
    await flush();

    const frame = lastSent(sock);
    expect(frame.type).toBe('join_session');
    expect(frame.session_id).toBe('s1');
    expect(typeof frame.id).toBe('string');
    expect(typeof frame.timestamp).toBe('number');
    expect(frame.version).toBe(2);
    expect(typeof frame.conn_id).toBe('string');

    sock.receive({ type: 'joined', session_id: 's1', request_id: frame.id });
    await expect(joinPromise).resolves.toBeUndefined();
  });

  it('joinSession while joined to a different session leaves the old one first', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const join1 = ws.joinSession('s1');
    sock.open();
    await flush();
    const joinFrame1 = lastSent(sock);
    sock.receive({ type: 'joined', session_id: 's1', request_id: joinFrame1.id });
    await join1;

    const join2 = ws.joinSession('s2');
    await flush();
    // leave_session for s1 should have been sent immediately (before the new join reply)
    const leaveFrame = JSON.parse(sock.sent[sock.sent.length - 2]);
    expect(leaveFrame.type).toBe('leave_session');
    expect(leaveFrame.session_id).toBe('s1');

    const joinFrame2 = lastSent(sock);
    expect(joinFrame2.type).toBe('join_session');
    expect(joinFrame2.session_id).toBe('s2');

    sock.receive({ type: 'joined', session_id: 's2', request_id: joinFrame2.id });
    await expect(join2).resolves.toBeUndefined();
  });

  it('joinSession request times out if no reply arrives', async () => {
    vi.useFakeTimers();
    vi.resetModules();
    const { getChatWebSocket, CHAT_WS_REQUEST_TIMEOUT_MS } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const joinPromise = ws.joinSession('s1');
    sock.open();
    await flush();

    const assertion = expect(joinPromise).rejects.toThrow(/timed out/);
    await vi.advanceTimersByTimeAsync(CHAT_WS_REQUEST_TIMEOUT_MS);
    await assertion;
  });

  it('dispatches event/status_update/error/stream_end messages to session handlers', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const joinPromise = ws.joinSession('s1');
    sock.open();
    await flush();
    const joinFrame = lastSent(sock);
    sock.receive({ type: 'joined', session_id: 's1', request_id: joinFrame.id });
    await joinPromise;

    const onEvent = vi.fn();
    const onStatusUpdate = vi.fn();
    const onError = vi.fn();
    const onStreamEnd = vi.fn();
    ws.setHandlers('s1', { onEvent, onStatusUpdate, onError, onStreamEnd });

    // plain event
    sock.receive({ type: 'event', session_id: 's1', event: 'message', data: { foo: 'bar' } });
    expect(onEvent).toHaveBeenCalledWith({ event: 'message', data: { foo: 'bar' } });

    // status_update event -> both onStatusUpdate and onEvent
    sock.receive({
      type: 'event',
      session_id: 's1',
      event: 'status_update',
      data: { agent_status: 'running' },
    });
    expect(onStatusUpdate).toHaveBeenCalledWith('running');
    expect(onEvent).toHaveBeenCalledWith({
      event: 'status_update',
      data: { agent_status: 'running' },
    });

    // unsolicited error (no matching pending request)
    sock.receive({ type: 'error', session_id: 's1', error: 'boom', code: 7 });
    expect(onError).toHaveBeenCalledWith('boom', 7);

    // stream_end
    sock.receive({ type: 'stream_end', session_id: 's1' });
    expect(onStreamEnd).toHaveBeenCalled();

    // clearHandlers -> no further calls, no throw
    ws.clearHandlers('s1');
    onEvent.mockClear();
    onStatusUpdate.mockClear();
    onError.mockClear();
    onStreamEnd.mockClear();
    expect(() => {
      sock.receive({ type: 'event', session_id: 's1', event: 'message', data: {} });
      sock.receive({ type: 'error', session_id: 's1', error: 'oops' });
      sock.receive({ type: 'stream_end', session_id: 's1' });
    }).not.toThrow();
    expect(onEvent).not.toHaveBeenCalled();
    expect(onStatusUpdate).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(onStreamEnd).not.toHaveBeenCalled();
  });

  it('reconnects after disconnect with exponential backoff and re-joins the previous session', async () => {
    vi.useFakeTimers();
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock0 = FakeWebSocket.instances[0];

    const joinPromise = ws.joinSession('s1');
    sock0.open();
    await flush();
    const joinFrame = lastSent(sock0);
    sock0.receive({ type: 'joined', session_id: 's1', request_id: joinFrame.id });
    await joinPromise;

    // First disconnect -> reconnect after 1000ms (initial reconnectDelay)
    sock0.close();
    expect(FakeWebSocket.instances.length).toBe(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeWebSocket.instances.length).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(2);

    const sock1 = FakeWebSocket.instances[1];
    sock1.open();
    await flush();
    const rejoinFrame = lastSent(sock1);
    expect(rejoinFrame.type).toBe('join_session');
    expect(rejoinFrame.session_id).toBe('s1');
  });

  it('doubles the reconnect backoff across consecutive failures (never reconnecting successfully in between)', async () => {
    vi.useFakeTimers();
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    getChatWebSocket();
    const sock0 = FakeWebSocket.instances[0];

    // First disconnect -> reconnect attempt after the initial 1000ms delay
    sock0.close();
    expect(FakeWebSocket.instances.length).toBe(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeWebSocket.instances.length).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(2);

    // Second disconnect without ever completing the reconnect (no open() call) ->
    // reconnectDelay was doubled to 2000ms before this connect attempt.
    FakeWebSocket.instances[1].close();
    await vi.advanceTimersByTimeAsync(1999);
    expect(FakeWebSocket.instances.length).toBe(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(3);
  });

  it('chat() joins first when not already joined, then sends chat and awaits ack', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const chatPromise = ws.chat({ sessionId: 's1', message: 'hi' });
    sock.open();
    await flush();

    const joinFrame = lastSent(sock);
    expect(joinFrame.type).toBe('join_session');
    expect(joinFrame.session_id).toBe('s1');
    sock.receive({ type: 'joined', session_id: 's1', request_id: joinFrame.id });

    // Allow the joinSession promise chain to progress before the chat frame is sent
    await flush();

    expect(sock.sent.length).toBe(2);
    const chatFrame = lastSent(sock);
    expect(chatFrame.type).toBe('chat');
    expect(chatFrame.session_id).toBe('s1');
    expect(chatFrame.message).toBe('hi');

    sock.receive({ type: 'ack', request_id: chatFrame.id, op: 'chat', session_id: 's1', ok: true });
    await expect(chatPromise).resolves.toBeUndefined();
  });

  it('stopSession sends stop_session and resolves on stopped', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const stopPromise = ws.stopSession('s1');
    sock.open();
    await flush();

    const frame = lastSent(sock);
    expect(frame.type).toBe('stop_session');
    expect(frame.session_id).toBe('s1');

    sock.receive({ type: 'stopped', session_id: 's1', request_id: frame.id });
    await expect(stopPromise).resolves.toBeUndefined();
  });

  it('destroy() closes the socket and rejects in-flight requests', async () => {
    vi.resetModules();
    const { getChatWebSocket } = await import('../chatWs');
    const ws = getChatWebSocket();
    const sock = FakeWebSocket.instances[0];

    const joinPromise = ws.joinSession('s1');
    sock.open();
    await flush();

    const assertion = expect(joinPromise).rejects.toThrow(/destroyed/);
    ws.destroy();
    await assertion;
    expect(sock.readyState).toBe(FakeWebSocket.CLOSED);
  });
});
