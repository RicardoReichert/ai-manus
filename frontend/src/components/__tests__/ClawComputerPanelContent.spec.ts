import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, onMounted } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en'
import ClawComputerPanelContent from '../ClawComputerPanelContent.vue'
import type { ClawToolLogEntry } from '@/api/claw'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

// ClawTerminalView opens a real xterm.js instance + a live ClawTerminalClient
// WebSocket — stub it the same way ComputerToolViews.e2e.spec.ts stubs
// MonacoEditor. This spec exercises ClawComputerPanelContent's own
// tab-switching/prop-passing, not terminal internals. mountCount lets the
// terminalResetKey tests assert a real unmount+remount happened (a fresh
// connection), not just a prop update on the same instance.
let terminalStubMountCount = 0
const ClawTerminalViewStub = defineComponent({
  name: 'ClawTerminalViewStub',
  props: ['sessionId'],
  setup() {
    onMounted(() => { terminalStubMountCount++ })
    return () => h('div', { class: 'terminal-stub' })
  },
})

function mountContent(props: {
  sessionId?: string
  presentation?: 'sidebar' | 'dialog'
  toolLog?: ClawToolLogEntry[]
  terminalResetKey?: number
} = {}) {
  return mount(ClawComputerPanelContent, {
    global: {
      plugins: [i18n],
      stubs: { ClawTerminalView: ClawTerminalViewStub },
    },
    props: { sessionId: 'sess-1', ...props },
  })
}

describe('ClawComputerPanelContent', () => {
  beforeEach(() => {
    terminalStubMountCount = 0
  })

  it('bumping terminalResetKey forces the terminal to fully unmount/remount (fresh connection)', async () => {
    const wrapper = mountContent({ terminalResetKey: 0 })
    await wrapper.findAll('button').find((b) => b.text() === 'Terminal')!.trigger('click')
    expect(terminalStubMountCount).toBe(1)

    // Same tab, same sessionId — only the reset key changes (this is exactly
    // what ClawPage does on session restart, since the session id itself
    // doesn't change across a restart).
    await wrapper.setProps({ terminalResetKey: 1 })

    expect(terminalStubMountCount).toBe(2)
    expect(wrapper.find('.terminal-stub').exists()).toBe(true)
  })

  it('switching sessionId also forces a fresh terminal connection', async () => {
    const wrapper = mountContent({ sessionId: 'sess-1' })
    await wrapper.findAll('button').find((b) => b.text() === 'Terminal')!.trigger('click')
    expect(terminalStubMountCount).toBe(1)

    await wrapper.setProps({ sessionId: 'sess-2' })

    expect(terminalStubMountCount).toBe(2)
  })

  it('defaults to the Tools tab and renders the real tool log', () => {
    const toolLog: ClawToolLogEntry[] = [
      { id: 'a', name: 'shell_exec', argsSummary: '', status: 'running', timestamp: Date.now() },
    ]
    const wrapper = mountContent({ toolLog })

    expect(wrapper.text()).toContain('shell_exec')
    expect(wrapper.text()).toContain('Running')
    expect(wrapper.find('.terminal-stub').exists()).toBe(false)
  })

  it('switches to Terminal mode when the Terminal tab is clicked', async () => {
    const wrapper = mountContent()

    await wrapper.findAll('button').find((b) => b.text() === 'Terminal')!.trigger('click')

    expect(wrapper.find('.terminal-stub').exists()).toBe(true)
  })

  it('switches back to Tools mode when the Tools tab is clicked', async () => {
    const wrapper = mountContent()

    await wrapper.findAll('button').find((b) => b.text() === 'Terminal')!.trigger('click')
    expect(wrapper.find('.terminal-stub').exists()).toBe(true)

    await wrapper.findAll('button').find((b) => b.text() === 'Tools')!.trigger('click')
    expect(wrapper.find('.terminal-stub').exists()).toBe(false)
  })

  it('only offers Terminal and Tools tabs (no Screen/Agent)', () => {
    const wrapper = mountContent()

    const labels = wrapper.findAll('button').map((b) => b.text())
    expect(labels).toContain('Terminal')
    expect(labels).toContain('Tools')
    expect(labels).not.toContain('Screen')
    expect(labels).not.toContain('Agent')
    expect(labels.some((l) => l.includes('Take control'))).toBe(false)
  })

  it('the Close button emits "hide"', async () => {
    const wrapper = mountContent()

    await wrapper.find('[title="Close"]').trigger('click')

    expect(wrapper.emitted('hide')).toHaveLength(1)
  })
})
