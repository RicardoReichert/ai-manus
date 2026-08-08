import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  BASE_URL: 'http://localhost:8000/api/v1',
}))

describe('api/claw', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  describe('getClawVncUrl', () => {
    it('builds the ws URL for the claw VNC proxy from BASE_URL', async () => {
      const { getClawVncUrl } = await import('../claw')

      const result = getClawVncUrl('session-123')

      expect(result).toBe('ws://localhost:8000/api/v1/ws/claw/vnc/session-123')
    })

    it('preserves https -> wss upgrade', async () => {
      vi.doMock('../client', () => ({
        apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
        BASE_URL: 'https://example.com/api/v1',
      }))

      const { getClawVncUrl } = await import('../claw')

      const result = getClawVncUrl('abc')

      expect(result).toBe('wss://example.com/api/v1/ws/claw/vnc/abc')
    })
  })

  describe('ClawTerminalClient', () => {
    /**
     * Minimal fake WebSocket, same shape/idiom as `chatWs.spec.ts`'s
     * FakeWebSocket — implements just the surface ClawTerminalClient touches.
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
      constructor(public url: string) { FakeWebSocket.instances.push(this) }
      static instances: FakeWebSocket[] = [];
      send(data: string) { this.sent.push(data) }
      close() { this.readyState = FakeWebSocket.CLOSED; this.onclose?.() }
      /** test helper */
      open() { this.readyState = FakeWebSocket.OPEN; this.onopen?.() }
      /** test helper */
      receive(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }) }
    }

    beforeEach(() => {
      // Reassert the default (http) client mock: an earlier test in this file
      // may have left an https override in place via vi.doMock, which
      // otherwise leaks into these tests since vi.resetModules() alone
      // doesn't undo a prior vi.doMock() call.
      vi.doMock('../client', () => ({
        apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
        BASE_URL: 'http://localhost:8000/api/v1',
      }))
      vi.stubGlobal('WebSocket', FakeWebSocket)
      FakeWebSocket.instances = []
    })

    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('connects to the terminal WS route, omitting cols/rows from the query when not passed', async () => {
      const { ClawTerminalClient } = await import('../claw')

      new ClawTerminalClient('sess-1', { onMessage: vi.fn() })

      expect(FakeWebSocket.instances.length).toBe(1)
      expect(FakeWebSocket.instances[0].url).toBe(
        'ws://localhost:8000/api/v1/ws/claw/terminal/sess-1'
      )
    })

    it('includes cols/rows as query params when passed', async () => {
      const { ClawTerminalClient } = await import('../claw')

      new ClawTerminalClient('sess-1', { onMessage: vi.fn() }, 80, 24)

      expect(FakeWebSocket.instances[0].url).toBe(
        'ws://localhost:8000/api/v1/ws/claw/terminal/sess-1?cols=80&rows=24'
      )
    })

    it('fires onOpen/onClose and forwards parsed messages to onMessage', async () => {
      const { ClawTerminalClient } = await import('../claw')
      const onOpen = vi.fn()
      const onClose = vi.fn()
      const onMessage = vi.fn()

      new ClawTerminalClient('sess-1', { onOpen, onClose, onMessage })
      const sock = FakeWebSocket.instances[0]

      sock.open()
      expect(onOpen).toHaveBeenCalledTimes(1)

      sock.receive({ type: 'data', seq: 1, data: 'hello\n' })
      expect(onMessage).toHaveBeenCalledWith({ type: 'data', seq: 1, data: 'hello\n' })

      sock.close()
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('silently ignores a malformed message instead of throwing', async () => {
      const { ClawTerminalClient } = await import('../claw')
      const onMessage = vi.fn()

      new ClawTerminalClient('sess-1', { onMessage })
      const sock = FakeWebSocket.instances[0]

      expect(() => sock.onmessage?.({ data: 'not json' })).not.toThrow()
      expect(onMessage).not.toHaveBeenCalled()
    })

    it('sendInput/resize send well-formed frames only while OPEN, and are no-ops otherwise', async () => {
      const { ClawTerminalClient } = await import('../claw')

      const client = new ClawTerminalClient('sess-1', { onMessage: vi.fn() })
      const sock = FakeWebSocket.instances[0]

      // Not yet open: no-op, nothing sent.
      client.sendInput('ls\n')
      expect(sock.sent.length).toBe(0)

      sock.open()
      client.sendInput('ls\n')
      client.resize(120, 40)

      expect(JSON.parse(sock.sent[0])).toEqual({ type: 'input', data: 'ls\n' })
      expect(JSON.parse(sock.sent[1])).toEqual({ type: 'resize', cols: 120, rows: 40 })
    })

    it('disconnect() closes the socket and isConnected reflects readyState', async () => {
      const { ClawTerminalClient } = await import('../claw')

      const client = new ClawTerminalClient('sess-1', { onMessage: vi.fn() })
      const sock = FakeWebSocket.instances[0]
      sock.open()

      expect(client.isConnected).toBe(true)

      client.disconnect()

      expect(sock.readyState).toBe(FakeWebSocket.CLOSED)
      expect(client.isConnected).toBe(false)
    })
  })
})
