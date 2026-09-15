import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useSessionSidebar } from '../useSessionSidebar'

describe('useSessionSidebar', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('default: isSessionSidebarShow.value === false when localStorage is empty', () => {
    const { isSessionSidebarShow } = useSessionSidebar()
    expect(isSessionSidebarShow.value).toBe(false)
  })

  it('reads persisted true from localStorage for manus-session-sidebar-state on module import', async () => {
    // Seed localStorage before dynamic import
    localStorage.setItem('manus-session-sidebar-state', 'true')

    // Dynamically import to trigger module initialization with seeded value
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow } = useSessionSidebarImported()

    expect(isSessionSidebarShow.value).toBe(true)
  })

  it('migrates from legacy manus-left-panel-state key and removes it', async () => {
    // Seed localStorage with legacy key only, no new key
    localStorage.setItem('manus-left-panel-state', 'true')

    // Dynamically import to trigger module initialization
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow } = useSessionSidebarImported()

    // Check that the value was migrated
    expect(isSessionSidebarShow.value).toBe(true)

    // Check that the new key was set
    expect(localStorage.getItem('manus-session-sidebar-state')).toBe('true')

    // Check that the legacy key was removed
    expect(localStorage.getItem('manus-left-panel-state')).toBe(null)
  })

  it('toggleSessionSidebar() flips the boolean each call', async () => {
    // Use dynamic import to get fresh module state
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow, toggleSessionSidebar } = useSessionSidebarImported()

    expect(isSessionSidebarShow.value).toBe(false)

    toggleSessionSidebar()
    expect(isSessionSidebarShow.value).toBe(true)

    toggleSessionSidebar()
    expect(isSessionSidebarShow.value).toBe(false)

    toggleSessionSidebar()
    expect(isSessionSidebarShow.value).toBe(true)
  })

  it('setSessionSidebar(true) sets isSessionSidebarShow.value to true and persists to localStorage', async () => {
    // Use dynamic import to get fresh module state
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow, setSessionSidebar } = useSessionSidebarImported()

    expect(isSessionSidebarShow.value).toBe(false)

    setSessionSidebar(true)
    expect(isSessionSidebarShow.value).toBe(true)

    // Wait for the watch to persist the value to localStorage
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-session-sidebar-state')).toBe('true')
    })
  })

  it('setSessionSidebar(false) sets isSessionSidebarShow.value to false and persists to localStorage', async () => {
    // Use dynamic import to get fresh module state
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow, setSessionSidebar } = useSessionSidebarImported()

    // First set to true
    setSessionSidebar(true)
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-session-sidebar-state')).toBe('true')
    })

    // Then set to false
    setSessionSidebar(false)
    expect(isSessionSidebarShow.value).toBe(false)

    // Wait for the watch to persist the value to localStorage
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-session-sidebar-state')).toBe('false')
    })
  })

  it('showSessionSidebar() sets isSessionSidebarShow.value to true and persists to localStorage', async () => {
    // Use dynamic import to get fresh module state
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow, showSessionSidebar } = useSessionSidebarImported()

    expect(isSessionSidebarShow.value).toBe(false)

    showSessionSidebar()
    expect(isSessionSidebarShow.value).toBe(true)

    // Wait for the watch to persist the value to localStorage
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-session-sidebar-state')).toBe('true')
    })
  })

  it('hideSessionSidebar() sets isSessionSidebarShow.value to false and persists to localStorage', async () => {
    // Use dynamic import to get fresh module state
    const mod = await import('../useSessionSidebar')
    const { useSessionSidebar: useSessionSidebarImported } = mod
    const { isSessionSidebarShow, hideSessionSidebar } = useSessionSidebarImported()

    // First set to true
    isSessionSidebarShow.value = true
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-session-sidebar-state')).toBe('true')
    })

    // Then hide
    hideSessionSidebar()
    expect(isSessionSidebarShow.value).toBe(false)

    // Wait for the watch to persist the value to localStorage
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-session-sidebar-state')).toBe('false')
    })
  })
})
