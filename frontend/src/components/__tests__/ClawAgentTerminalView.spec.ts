import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { Terminal } from '@xterm/xterm'
import en from '@/locales/en'
import ClawAgentTerminalView from '../ClawAgentTerminalView.vue'
import type { ClawEvent } from '@/api/claw'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

function toolEvent(partial: Partial<ClawEvent>): ClawEvent {
  return { type: 'tool', toolCallId: 'call-1', ...partial }
}

beforeAll(() => {
  // jsdom lacks matchMedia and ResizeObserver; xterm.js needs both.
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = RO as unknown as typeof ResizeObserver
})

describe('ClawAgentTerminalView', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('shows the empty state until the first tool event arrives', async () => {
    const wrapper = mount(ClawAgentTerminalView, {
      global: { plugins: [i18n] },
      props: { event: null },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r, 20))

    expect(wrapper.text()).toContain('No agent activity yet')

    wrapper.unmount()
  })

  it('writes a cyan "$ name args" prompt line on phase start, and clears the empty state', async () => {
    const writeSpy = vi.spyOn(Terminal.prototype, 'write')
    const wrapper = mount(ClawAgentTerminalView, {
      global: { plugins: [i18n] },
      props: { event: null },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r, 20))

    await wrapper.setProps({
      event: toolEvent({ phase: 'start', name: 'shell_exec', args: { command: 'ls -la' } }),
    })
    await new Promise((r) => setTimeout(r, 20))

    const written = writeSpy.mock.calls.map((c) => c[0]).join('')
    expect(written).toContain('$ shell_exec')
    expect(written).toContain('ls -la')
    expect(written).toContain('\x1b[36m') // cyan
    expect(wrapper.text()).not.toContain('No agent activity yet')

    wrapper.unmount()
  })

  it('streams update partialResult text incrementally without an extra prompt line', async () => {
    const writeSpy = vi.spyOn(Terminal.prototype, 'write')
    const wrapper = mount(ClawAgentTerminalView, {
      global: { plugins: [i18n] },
      props: { event: toolEvent({ phase: 'start', name: 'shell_exec', args: { command: 'ls' } }) },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r, 20))
    writeSpy.mockClear()

    await wrapper.setProps({
      event: toolEvent({ phase: 'update', name: 'shell_exec', partialResult: 'file1.txt\n' }),
    })
    await new Promise((r) => setTimeout(r, 20))

    const written = writeSpy.mock.calls.map((c) => c[0]).join('')
    expect(written).toContain('file1.txt')
    expect(written).not.toContain('$ shell_exec')

    wrapper.unmount()
  })

  it('writes the result in red when isError', async () => {
    const writeSpy = vi.spyOn(Terminal.prototype, 'write')
    const wrapper = mount(ClawAgentTerminalView, {
      global: { plugins: [i18n] },
      props: { event: null },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r, 20))

    await wrapper.setProps({
      event: toolEvent({ phase: 'result', name: 'shell_exec', result: 'boom', isError: true, toolCallId: 'call-err' }),
    })
    await new Promise((r) => setTimeout(r, 20))

    const written = writeSpy.mock.calls.map((c) => c[0]).join('')
    expect(written).toContain('\x1b[31m') // red
    expect(written).toContain('boom')

    wrapper.unmount()
  })

  it('stringifies a non-string result (e.g. an object) instead of writing [object Object]', async () => {
    const writeSpy = vi.spyOn(Terminal.prototype, 'write')
    const wrapper = mount(ClawAgentTerminalView, {
      global: { plugins: [i18n] },
      props: { event: null },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r, 20))

    await wrapper.setProps({
      event: toolEvent({ phase: 'result', name: 'file_write', result: { bytes_written: 12 }, toolCallId: 'call-2' }),
    })
    await new Promise((r) => setTimeout(r, 20))

    const written = writeSpy.mock.calls.map((c) => c[0]).join('')
    expect(written).toContain('bytes_written')
    expect(written).not.toContain('[object Object]')

    wrapper.unmount()
  })

  it('writes the initial event passed at mount time, not just subsequent prop changes', async () => {
    const writeSpy = vi.spyOn(Terminal.prototype, 'write')
    const wrapper = mount(ClawAgentTerminalView, {
      global: { plugins: [i18n] },
      props: { event: toolEvent({ phase: 'start', name: 'shell_exec', args: { command: 'pwd' } }) },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r, 20))

    const written = writeSpy.mock.calls.map((c) => c[0]).join('')
    expect(written).toContain('$ shell_exec')
    expect(written).toContain('pwd')

    wrapper.unmount()
  })
})
