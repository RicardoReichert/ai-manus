import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getStoredToken } from '../../api/auth'
import { getCachedClientConfig } from '../../api/config'

vi.mock('../../api/auth', () => ({
  getStoredToken: vi.fn(),
  // LoginPage.vue transitively imports src/api/index.ts, which calls
  // initializeAuth() at module load time; the mock must provide it too.
  initializeAuth: vi.fn()
}))

vi.mock('../../api/config', () => ({
  getCachedClientConfig: vi.fn()
}))

const mockedGetStoredToken = vi.mocked(getStoredToken)
const mockedGetCachedClientConfig = vi.mocked(getCachedClientConfig)

// Real navigation lazy-loads real page components (MainLayout, LoginPage,
// ShareLayout and their children); under full-suite parallel load this can
// exceed the default 5s test timeout, so it's raised here.
describe('router auth guard', { timeout: 20000 }, () => {
  beforeEach(() => {
    vi.resetModules()
    mockedGetStoredToken.mockReset()
    mockedGetCachedClientConfig.mockReset()
  })

  async function loadRouter() {
    const { router } = await import('../index')
    return router
  }

  it('allows navigation to a requiresAuth route when auth_provider is none', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'none',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue(null)

    const router = await loadRouter()
    await router.push('/library')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/library')
  })

  it('allows navigation to a requiresAuth route when client config fetch failed (null)', async () => {
    mockedGetCachedClientConfig.mockResolvedValue(null)
    mockedGetStoredToken.mockReturnValue(null)

    const router = await loadRouter()
    await router.push('/library')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/library')
  })

  it('redirects to /login with redirect query when auth is required and no token', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'password',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue(null)

    const router = await loadRouter()
    await router.push('/library')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/library')
  })

  it('allows navigation to a requiresAuth route when a token is present', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'password',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue('sometoken')

    const router = await loadRouter()
    await router.push('/library')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/library')
  })

  it('redirects away from /login to / when auth_provider is none', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'none',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue(null)

    const router = await loadRouter()
    await router.push('/login')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/')
  })

  it('redirects away from /login to / when a real provider and token are present', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'password',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue('sometoken')

    const router = await loadRouter()
    await router.push('/login')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/')
  })

  it('stays on /login (no redirect loop) with a real provider and no token', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'password',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue(null)

    const router = await loadRouter()
    await router.push('/login')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('allows navigation to a public route (/share/:sessionId) with no token and a real provider', async () => {
    mockedGetCachedClientConfig.mockResolvedValue({
      auth_provider: 'password',
      show_github_button: false,
      github_repository_url: '',
      google_analytics_id: null,
      claw_enabled: false
    })
    mockedGetStoredToken.mockReturnValue(null)

    const router = await loadRouter()
    await router.push('/share/abc123')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/share/abc123')
  })
})
