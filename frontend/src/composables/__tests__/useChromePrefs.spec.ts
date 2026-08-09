import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useChromePrefs } from '../useChromePrefs'

describe('useChromePrefs', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('default: browserNotificationsEnabled.value === false when localStorage is empty', () => {
    const { browserNotificationsEnabled } = useChromePrefs()
    expect(browserNotificationsEnabled.value).toBe(false)
  })

  it('default: soundReminderEnabled.value === false when localStorage is empty', () => {
    const { soundReminderEnabled } = useChromePrefs()
    expect(soundReminderEnabled.value).toBe(false)
  })

  it('reads persisted true from localStorage for manus-browser-notifications on module import', async () => {
    // Seed localStorage before dynamic import
    localStorage.setItem('manus-browser-notifications', 'true')

    // Reset modules to trigger fresh import with seeded localStorage
    vi.resetModules()

    // Dynamically import to trigger module initialization with seeded value
    const mod = await import('../useChromePrefs')
    const { useChromePrefs: useChromePrefsImported } = mod
    const { browserNotificationsEnabled } = useChromePrefsImported()

    expect(browserNotificationsEnabled.value).toBe(true)
  })

  it('setSoundReminder(true) sets soundReminderEnabled.value to true and persists to localStorage', async () => {
    const { soundReminderEnabled, setSoundReminder } = useChromePrefs()
    setSoundReminder(true)
    expect(soundReminderEnabled.value).toBe(true)
    // Wait for the watch to persist the value to localStorage
    await vi.waitFor(() => {
      expect(localStorage.getItem('manus-sound-reminder')).toBe('true')
    })
  })

  it('setBrowserNotifications(true) when Notification is undefined → sets ref to false and resolves false', async () => {
    // Ensure Notification is not defined
    const originalNotification = globalThis.Notification
    // @ts-expect-error - intentionally removing Notification for this test
    delete globalThis.Notification

    const { browserNotificationsEnabled, setBrowserNotifications } = useChromePrefs()
    const result = await setBrowserNotifications(true)

    expect(result).toBe(false)
    expect(browserNotificationsEnabled.value).toBe(false)

    // Restore
    if (originalNotification) {
      globalThis.Notification = originalNotification
    }
  })

  it('setBrowserNotifications(true) with Notification.requestPermission returning "granted" → resolves true and sets ref true', async () => {
    const mockRequestPermission = vi.fn().mockResolvedValue('granted')
    // @ts-expect-error - stubbing global Notification with a minimal mock
    globalThis.Notification = { requestPermission: mockRequestPermission }

    const { browserNotificationsEnabled, setBrowserNotifications } = useChromePrefs()
    const result = await setBrowserNotifications(true)

    expect(result).toBe(true)
    expect(browserNotificationsEnabled.value).toBe(true)
    expect(mockRequestPermission).toHaveBeenCalled()

    // Clean up
    // @ts-expect-error - intentionally removing Notification for other tests
    delete globalThis.Notification
  })

  it('setBrowserNotifications(true) with Notification.requestPermission returning "denied" → resolves false and ref stays false', async () => {
    const mockRequestPermission = vi.fn().mockResolvedValue('denied')
    // @ts-expect-error - stubbing global Notification with a minimal mock
    globalThis.Notification = { requestPermission: mockRequestPermission }

    const { browserNotificationsEnabled, setBrowserNotifications } = useChromePrefs()
    const result = await setBrowserNotifications(true)

    expect(result).toBe(false)
    expect(browserNotificationsEnabled.value).toBe(false)
    expect(mockRequestPermission).toHaveBeenCalled()

    // Clean up
    // @ts-expect-error - intentionally removing Notification for other tests
    delete globalThis.Notification
  })

  it('setBrowserNotifications(false) → sets ref to false and resolves true without touching Notification', async () => {
    // @ts-expect-error - intentionally removing Notification for this test
    delete globalThis.Notification

    const { browserNotificationsEnabled, setBrowserNotifications } = useChromePrefs()
    const result = await setBrowserNotifications(false)

    expect(result).toBe(true)
    expect(browserNotificationsEnabled.value).toBe(false)
  })
})
