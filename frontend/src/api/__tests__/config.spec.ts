import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

describe('api/config', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  describe('getClientConfig', () => {
    it('calls apiClient.get("/config/frontend") and returns response.data.data', async () => {
      const mockConfig = {
        auth_provider: 'none',
        show_github_button: false,
        github_repository_url: '',
        google_analytics_id: null,
        claw_enabled: false,
      }

      const mockResponse = {
        data: {
          data: mockConfig,
        },
      }

      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const { getClientConfig } = await import('../config')
      const result = await getClientConfig()

      expect(result).toEqual(mockConfig)
      expect(result.auth_provider).toBe('none')
      expect(apiClient.get).toHaveBeenCalledWith('/config/frontend')
    })
  })

  describe('getCachedClientConfig', () => {
    it('calls apiClient.get once on first call and returns the config', async () => {
      const mockConfig = {
        auth_provider: 'google',
        show_github_button: true,
        github_repository_url: 'https://github.com/example/repo',
        google_analytics_id: 'GA-123',
        claw_enabled: true,
      }

      const mockResponse = {
        data: {
          data: mockConfig,
        },
      }

      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const { getCachedClientConfig } = await import('../config')
      const result = await getCachedClientConfig()

      expect(result).toEqual(mockConfig)
      expect(apiClient.get).toHaveBeenCalledTimes(1)
    })

    it('does not call apiClient.get again on second call (same module instance)', async () => {
      const mockConfig = {
        auth_provider: 'google',
        show_github_button: true,
        github_repository_url: 'https://github.com/example/repo',
        google_analytics_id: 'GA-123',
        claw_enabled: true,
      }

      const mockResponse = {
        data: {
          data: mockConfig,
        },
      }

      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const { getCachedClientConfig } = await import('../config')

      const result1 = await getCachedClientConfig()
      const result2 = await getCachedClientConfig()

      expect(result1).toEqual(mockConfig)
      expect(result2).toEqual(mockConfig)
      expect(apiClient.get).toHaveBeenCalledTimes(1)
    })

    it('returns null when fetch fails and does not retry on subsequent call', async () => {
      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockRejectedValue(new Error('Network error'))

      const { getCachedClientConfig } = await import('../config')

      const result1 = await getCachedClientConfig()
      const result2 = await getCachedClientConfig()

      expect(result1).toBeNull()
      expect(result2).toBeNull()
      expect(apiClient.get).toHaveBeenCalledTimes(1)
    })
  })

  describe('getCachedAuthProvider', () => {
    it('returns auth_provider from cached config when successful', async () => {
      const mockConfig = {
        auth_provider: 'github',
        show_github_button: true,
        github_repository_url: 'https://github.com/example/repo',
        google_analytics_id: 'GA-123',
        claw_enabled: true,
      }

      const mockResponse = {
        data: {
          data: mockConfig,
        },
      }

      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const { getCachedAuthProvider } = await import('../config')
      const result = await getCachedAuthProvider()

      expect(result).toBe('github')
    })

    it('returns null when cached config is null (fetch failed)', async () => {
      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockRejectedValue(new Error('Network error'))

      const { getCachedAuthProvider } = await import('../config')
      const result = await getCachedAuthProvider()

      expect(result).toBeNull()
    })

    it('returns null when auth_provider is falsy', async () => {
      const mockConfig = {
        auth_provider: '',
        show_github_button: true,
        github_repository_url: 'https://github.com/example/repo',
        google_analytics_id: 'GA-123',
        claw_enabled: true,
      }

      const mockResponse = {
        data: {
          data: mockConfig,
        },
      }

      const { apiClient } = await import('../client')
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const { getCachedAuthProvider } = await import('../config')
      const result = await getCachedAuthProvider()

      expect(result).toBeNull()
    })
  })
})
