import { describe, it, expect, beforeEach, vi } from 'vitest'

describe('useShortcuts', () => {
  beforeEach(() => {
    localStorage.clear()
    // Each test needs a fresh module instance — the composable's bindings
    // ref is module-level state seeded once (from localStorage / platform
    // detection) at import time.
    vi.resetModules()
  })

  it('defaults new-task to Ctrl+K on non-Mac', async () => {
    Object.defineProperty(window.navigator, 'platform', { value: 'Win32', configurable: true })
    const { useShortcuts } = await import('../useShortcuts')
    const { bindings } = useShortcuts()
    expect(bindings.value['new-task']).toEqual({
      ctrl: true, meta: false, shift: false, alt: false, key: 'k',
    })
  })

  it('defaults new-task to Cmd+K on Mac', async () => {
    Object.defineProperty(window.navigator, 'platform', { value: 'MacIntel', configurable: true })
    const { useShortcuts } = await import('../useShortcuts')
    const { bindings } = useShortcuts()
    expect(bindings.value['new-task']).toEqual({
      ctrl: false, meta: true, shift: false, alt: false, key: 'k',
    })
  })

  it('matches a KeyboardEvent against the current binding', async () => {
    Object.defineProperty(window.navigator, 'platform', { value: 'Win32', configurable: true })
    const { useShortcuts } = await import('../useShortcuts')
    const { matches } = useShortcuts()
    const event = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true })
    expect(matches('new-task', event)).toBe(true)
    const wrongKey = new KeyboardEvent('keydown', { key: 'j', ctrlKey: true })
    expect(matches('new-task', wrongKey)).toBe(false)
    const missingModifier = new KeyboardEvent('keydown', { key: 'k' })
    expect(matches('new-task', missingModifier)).toBe(false)
  })

  it('setBinding updates state, persists to localStorage, and matches() picks it up', async () => {
    Object.defineProperty(window.navigator, 'platform', { value: 'Win32', configurable: true })
    const { useShortcuts } = await import('../useShortcuts')
    const { setBinding, matches, bindings } = useShortcuts()
    setBinding('new-task', { ctrl: false, meta: false, shift: true, alt: true, key: 'p' })

    expect(bindings.value['new-task']).toEqual({
      ctrl: false, meta: false, shift: true, alt: true, key: 'p',
    })
    const event = new KeyboardEvent('keydown', { key: 'p', shiftKey: true, altKey: true })
    expect(matches('new-task', event)).toBe(true)
    expect(JSON.parse(localStorage.getItem('manus-shortcut-new-task') || '{}')).toEqual({
      ctrl: false, meta: false, shift: true, alt: true, key: 'p',
    })
  })

  it('a rebound shortcut survives a fresh module load (persists across reload)', async () => {
    localStorage.setItem(
      'manus-shortcut-new-task',
      JSON.stringify({ ctrl: false, meta: false, shift: true, alt: false, key: 'n' }),
    )
    const { useShortcuts } = await import('../useShortcuts')
    const { bindings } = useShortcuts()
    expect(bindings.value['new-task']).toEqual({
      ctrl: false, meta: false, shift: true, alt: false, key: 'n',
    })
  })

  it('resetBinding restores the platform default', async () => {
    Object.defineProperty(window.navigator, 'platform', { value: 'Win32', configurable: true })
    const { useShortcuts } = await import('../useShortcuts')
    const { setBinding, resetBinding, bindings } = useShortcuts()
    setBinding('new-task', { ctrl: false, meta: false, shift: true, alt: false, key: 'n' })
    resetBinding('new-task')
    expect(bindings.value['new-task']).toEqual({
      ctrl: true, meta: false, shift: false, alt: false, key: 'k',
    })
  })

  it('formatBinding renders modifier symbols in a stable order', async () => {
    Object.defineProperty(window.navigator, 'platform', { value: 'Win32', configurable: true })
    const { useShortcuts } = await import('../useShortcuts')
    const { formatBinding } = useShortcuts()
    expect(formatBinding({ ctrl: true, meta: false, shift: false, alt: false, key: 'k' })).toEqual(['Ctrl', 'K'])
    expect(formatBinding({ ctrl: false, meta: false, shift: true, alt: true, key: 'p' }))
      .toEqual(['Alt', 'Shift', 'P'])
  })
})
