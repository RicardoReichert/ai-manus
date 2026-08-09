import { describe, it, expect, beforeEach } from 'vitest'
import { useSettingsDialog } from '../useSettingsDialog'

describe('useSettingsDialog', () => {
  beforeEach(() => {
    // Reset state before each test
    const { closeSettingsDialog, setDefaultTab } = useSettingsDialog()
    closeSettingsDialog()
    setDefaultTab('general')
  })

  it('openSettingsDialog() with no arg opens dialog without changing defaultTab', () => {
    const { isSettingsDialogOpen, defaultTab, openSettingsDialog, setDefaultTab } = useSettingsDialog()
    setDefaultTab('account')
    const previousTab = defaultTab.value

    openSettingsDialog()

    expect(isSettingsDialogOpen.value).toBe(true)
    expect(defaultTab.value).toBe(previousTab)
  })

  it("openSettingsDialog('account') sets defaultTab to 'account' and opens dialog", () => {
    const { isSettingsDialogOpen, defaultTab, openSettingsDialog } = useSettingsDialog()

    openSettingsDialog('account')

    expect(defaultTab.value).toBe('account')
    expect(isSettingsDialogOpen.value).toBe(true)
  })

  it("openSettingsDialog('settings') legacy alias sets defaultTab to 'general'", () => {
    const { isSettingsDialogOpen, defaultTab, openSettingsDialog } = useSettingsDialog()

    openSettingsDialog('settings')

    expect(defaultTab.value).toBe('general')
    expect(isSettingsDialogOpen.value).toBe(true)
  })

  it("openSettingsDialog('not-a-real-tab') opens dialog but leaves defaultTab unchanged", () => {
    const { isSettingsDialogOpen, defaultTab, openSettingsDialog, setDefaultTab } = useSettingsDialog()
    setDefaultTab('help')
    const previousTab = defaultTab.value

    openSettingsDialog('not-a-real-tab')

    expect(isSettingsDialogOpen.value).toBe(true)
    expect(defaultTab.value).toBe(previousTab)
  })

  it('closeSettingsDialog() closes the dialog', () => {
    const { isSettingsDialogOpen, openSettingsDialog, closeSettingsDialog } = useSettingsDialog()
    openSettingsDialog()

    closeSettingsDialog()

    expect(isSettingsDialogOpen.value).toBe(false)
  })

  it('toggleSettingsDialog() flips the boolean state', () => {
    const { isSettingsDialogOpen, toggleSettingsDialog } = useSettingsDialog()
    const initialState = isSettingsDialogOpen.value

    toggleSettingsDialog()

    expect(isSettingsDialogOpen.value).toBe(!initialState)

    toggleSettingsDialog()

    expect(isSettingsDialogOpen.value).toBe(initialState)
  })

  it("setDefaultTab('help') sets defaultTab without changing isSettingsDialogOpen", () => {
    const { isSettingsDialogOpen, defaultTab, setDefaultTab, openSettingsDialog, closeSettingsDialog } = useSettingsDialog()

    // Test with dialog open
    openSettingsDialog()
    const wasOpen = isSettingsDialogOpen.value

    setDefaultTab('help')

    expect(defaultTab.value).toBe('help')
    expect(isSettingsDialogOpen.value).toBe(wasOpen)

    // Test with dialog closed
    closeSettingsDialog()
    const wasClosed = isSettingsDialogOpen.value

    setDefaultTab('shortcuts')

    expect(defaultTab.value).toBe('shortcuts')
    expect(isSettingsDialogOpen.value).toBe(wasClosed)
  })
})
