import { describe, it, expect, vi, beforeEach } from 'vitest'

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
})
