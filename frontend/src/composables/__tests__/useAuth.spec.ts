import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useAuth } from '../useAuth'
import { eventBus } from '../../utils/eventBus'
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  logoutAll as apiLogoutAll,
  getCurrentUser,
  refreshToken as apiRefreshToken,
  setAuthToken,
  clearAuthToken,
  storeToken,
  storeRefreshToken,
  getStoredToken,
  getStoredRefreshToken,
  clearStoredTokens
} from '../../api/auth'
import { getCachedAuthProvider } from '../../api/config'

vi.mock('../../api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  logoutAll: vi.fn(),
  getCurrentUser: vi.fn(),
  refreshToken: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  storeToken: vi.fn(),
  storeRefreshToken: vi.fn(),
  getStoredToken: vi.fn(),
  getStoredRefreshToken: vi.fn(),
  clearStoredTokens: vi.fn()
}))

vi.mock('../../api/config', () => ({
  getCachedAuthProvider: vi.fn()
}))

function withSetup<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setup()
        return () => null
      }
    })
  )
  return { result, wrapper }
}

const user = {
  id: 'u1',
  fullname: 'Test User',
  email: 'test@example.com',
  role: 'user' as const,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}

const adminUser = { ...user, id: 'u2', role: 'admin' as const }

const loginResponse = {
  user,
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer'
}

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCachedAuthProvider).mockResolvedValue(null)
    vi.mocked(getStoredToken).mockReturnValue(null)
    vi.mocked(getStoredRefreshToken).mockReturnValue(null)
    // Clear any leftover state from a previous test (module state persists
    // across `it()` blocks since the module is imported once for the file).
    useAuth().clearAuth()
  })

  it('login on success stores tokens and sets user state', async () => {
    vi.mocked(apiLogin).mockResolvedValue(loginResponse)
    const auth = useAuth()

    const result = await auth.login({ email: user.email, password: 'pw' })

    expect(apiLogin).toHaveBeenCalledWith({ email: user.email, password: 'pw' })
    expect(storeToken).toHaveBeenCalledWith('access-1')
    expect(storeRefreshToken).toHaveBeenCalledWith('refresh-1')
    expect(setAuthToken).toHaveBeenCalledWith('access-1')
    expect(auth.currentUser.value).toEqual(user)
    expect(auth.isAuthenticated.value).toBe(true)
    expect(result).toEqual(loginResponse)
  })

  it('login on rejection sets authError, ends loading false, and rethrows', async () => {
    const error = new Error('bad credentials')
    vi.mocked(apiLogin).mockRejectedValue(error)
    const auth = useAuth()

    await expect(auth.login({ email: user.email, password: 'pw' })).rejects.toThrow(
      'bad credentials'
    )
    expect(auth.authError.value).toBe('bad credentials')
    expect(auth.isLoading.value).toBe(false)
  })

  it('register on success stores tokens and sets user state', async () => {
    const registerResponse = { ...loginResponse }
    vi.mocked(apiRegister).mockResolvedValue(registerResponse)
    const auth = useAuth()

    const result = await auth.register({
      fullname: user.fullname,
      email: user.email,
      password: 'pw'
    })

    expect(apiRegister).toHaveBeenCalled()
    expect(storeToken).toHaveBeenCalledWith('access-1')
    expect(storeRefreshToken).toHaveBeenCalledWith('refresh-1')
    expect(setAuthToken).toHaveBeenCalledWith('access-1')
    expect(auth.currentUser.value).toEqual(user)
    expect(auth.isAuthenticated.value).toBe(true)
    expect(result).toEqual(registerResponse)
  })

  it('register on rejection sets authError, ends loading false, and rethrows', async () => {
    const error = new Error('email taken')
    vi.mocked(apiRegister).mockRejectedValue(error)
    const auth = useAuth()

    await expect(
      auth.register({ fullname: user.fullname, email: user.email, password: 'pw' })
    ).rejects.toThrow('email taken')
    expect(auth.authError.value).toBe('email taken')
    expect(auth.isLoading.value).toBe(false)
  })

  it('logout (not silent) calls apiLogout then clears local state', async () => {
    vi.mocked(apiLogin).mockResolvedValue(loginResponse)
    vi.mocked(apiLogout).mockResolvedValue({})
    const auth = useAuth()
    await auth.login({ email: user.email, password: 'pw' })

    await auth.logout()

    expect(apiLogout).toHaveBeenCalled()
    expect(auth.currentUser.value).toBeNull()
    expect(auth.isAuthenticated.value).toBe(false)
    expect(clearAuthToken).toHaveBeenCalled()
    expect(clearStoredTokens).toHaveBeenCalled()
  })

  it('logout(true) (silent) does not call apiLogout but still clears local state', async () => {
    vi.mocked(apiLogin).mockResolvedValue(loginResponse)
    const auth = useAuth()
    await auth.login({ email: user.email, password: 'pw' })

    await auth.logout(true)

    expect(apiLogout).not.toHaveBeenCalled()
    expect(auth.currentUser.value).toBeNull()
    expect(auth.isAuthenticated.value).toBe(false)
    expect(clearAuthToken).toHaveBeenCalled()
    expect(clearStoredTokens).toHaveBeenCalled()
  })

  it('logoutAll calls apiLogoutAll then clears local state even when it rejects', async () => {
    vi.mocked(apiLogin).mockResolvedValue(loginResponse)
    vi.mocked(apiLogoutAll).mockRejectedValue(new Error('network error'))
    const auth = useAuth()
    await auth.login({ email: user.email, password: 'pw' })

    await auth.logoutAll()

    expect(apiLogoutAll).toHaveBeenCalled()
    expect(auth.currentUser.value).toBeNull()
    expect(auth.isAuthenticated.value).toBe(false)
    expect(clearAuthToken).toHaveBeenCalled()
    expect(clearStoredTokens).toHaveBeenCalled()
  })

  it('refreshAuthToken returns false and clears auth when no refresh token stored', async () => {
    vi.mocked(getStoredRefreshToken).mockReturnValue(undefined as unknown as string)
    const auth = useAuth()

    const result = await auth.refreshAuthToken()

    expect(result).toBe(false)
    expect(apiRefreshToken).not.toHaveBeenCalled()
    expect(auth.currentUser.value).toBeNull()
    expect(auth.isAuthenticated.value).toBe(false)
  })

  it('refreshAuthToken stores new access token and returns true on success', async () => {
    vi.mocked(getStoredRefreshToken).mockReturnValue('refresh-1')
    vi.mocked(apiRefreshToken).mockResolvedValue({
      access_token: 'access-2',
      token_type: 'bearer'
    })
    const auth = useAuth()

    const result = await auth.refreshAuthToken()

    expect(apiRefreshToken).toHaveBeenCalledWith({ refresh_token: 'refresh-1' })
    expect(storeToken).toHaveBeenCalledWith('access-2')
    expect(setAuthToken).toHaveBeenCalledWith('access-2')
    expect(result).toBe(true)
  })

  it('refreshAuthToken clears auth and returns false when apiRefreshToken rejects', async () => {
    vi.mocked(getStoredRefreshToken).mockReturnValue('refresh-1')
    vi.mocked(apiRefreshToken).mockRejectedValue(new Error('expired'))
    const auth = useAuth()

    const result = await auth.refreshAuthToken()

    expect(result).toBe(false)
    expect(auth.currentUser.value).toBeNull()
    expect(auth.isAuthenticated.value).toBe(false)
  })

  it('hasRole and isAdmin reflect the logged-in user role', async () => {
    vi.mocked(apiLogin).mockResolvedValue({ ...loginResponse, user: adminUser })
    const auth = useAuth()

    await auth.login({ email: adminUser.email, password: 'pw' })

    expect(auth.hasRole('admin')).toBe(true)
    expect(auth.isAdmin.value).toBe(true)
    expect(auth.hasRole('user')).toBe(false)
  })

  it('auth:logout eventBus emission triggers a silent logout via the mounted listener', async () => {
    vi.mocked(apiLogin).mockResolvedValue(loginResponse)
    const { result: auth, wrapper } = withSetup(() => useAuth())
    await auth.login({ email: user.email, password: 'pw' })

    eventBus.emit('auth:logout')
    // logout(true) is async; flush microtasks.
    await Promise.resolve()
    await Promise.resolve()

    expect(apiLogout).not.toHaveBeenCalled()
    expect(auth.currentUser.value).toBeNull()
    expect(auth.isAuthenticated.value).toBe(false)
    expect(clearAuthToken).toHaveBeenCalled()
    expect(clearStoredTokens).toHaveBeenCalled()

    wrapper.unmount()
  })
})
