import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en'
import ClawComputerPanelContent from '../ClawComputerPanelContent.vue'
import { eventBus } from '@/utils/eventBus'
import { getClawVncUrl, type ClawEvent, type ClawToolLogEntry } from '@/api/claw'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

// VNCViewer (real noVNC RFB) and ClawTerminalView (real xterm.js + a live
// ClawTerminalClient WebSocket) are heavy, connection-opening dependencies —
// stub them the same way ComputerToolViews.e2e.spec.ts stubs MonacoEditor.
// This spec exercises ClawComputerPanelContent's own mode-switching,
// take-control, and degraded-VNC-state wiring, not VNC/terminal internals.
const VNCViewerStub = defineComponent({
  name: 'VNCViewerStub',
  props: ['sessionId', 'enabled', 'urlResolver'],
  emits: ['connected', 'disconnected'],
  setup(props) {
    return () => h('div', { class: 'vnc-stub' }, String(props.urlResolver?.(props.sessionId)))
  },
})

const ClawTerminalViewStub = defineComponent({
  name: 'ClawTerminalViewStub',
  props: ['sessionId'],
  setup() {
    return () => h('div', { class: 'terminal-stub' })
  },
})

// Real xterm.js setup/teardown for ClawAgentTerminalView is covered by its
// own spec (ClawAgentTerminalView.spec.ts) — stub it here too so this file
// stays focused on ClawComputerPanelContent's own tab-switching/prop-passing.
const ClawAgentTerminalViewStub = defineComponent({
  name: 'ClawAgentTerminalViewStub',
  props: ['event'],
  setup(props) {
    return () => h('div', { class: 'agent-stub' }, props.event ? JSON.stringify(props.event) : '')
  },
})

function mountContent(props: {
  sessionId?: string
  presentation?: 'sidebar' | 'dialog'
  toolLog?: ClawToolLogEntry[]
  agentToolEvent?: ClawEvent | null
  initialView?: 'screen' | 'agent' | 'terminal' | 'tools'
} = {}) {
  return mount(ClawComputerPanelContent, {
    global: {
      plugins: [i18n],
      stubs: {
        VNCViewer: VNCViewerStub,
        ClawTerminalView: ClawTerminalViewStub,
        ClawAgentTerminalView: ClawAgentTerminalViewStub,
      },
    },
    props: { sessionId: 'sess-1', ...props },
  })
}

describe('ClawComputerPanelContent', () => {
  afterEach(() => {
    eventBus.all.clear()
  })

  it('defaults to Screen mode and renders the VNC view resolved via getClawVncUrl', () => {
    const wrapper = mountContent()

    const vnc = wrapper.find('.vnc-stub')
    expect(vnc.exists()).toBe(true)
    expect(vnc.text()).toBe(getClawVncUrl('sess-1'))
    expect(wrapper.find('.terminal-stub').exists()).toBe(false)
  })

  it('switches to Terminal mode when the Terminal tab is clicked', async () => {
    const wrapper = mountContent()

    await wrapper.findAll('button').find((b) => b.text() === 'Terminal')!.trigger('click')

    expect(wrapper.find('.terminal-stub').exists()).toBe(true)
    expect(wrapper.find('.vnc-stub').exists()).toBe(false)
  })

  it('switches to Tools mode and renders the real tool log with entries', async () => {
    const toolLog: ClawToolLogEntry[] = [
      { id: 'a', name: 'shell_exec', argsSummary: '', status: 'running', timestamp: Date.now() },
    ]
    const wrapper = mountContent({ toolLog })

    await wrapper.findAll('button').find((b) => b.text() === 'Tools')!.trigger('click')

    expect(wrapper.text()).toContain('shell_exec')
    expect(wrapper.text()).toContain('Running')
  })

  it('shows the inactive-computer empty state after VNC disconnects, and clears it once sessionId changes', async () => {
    const wrapper = mountContent()

    await wrapper.findComponent(VNCViewerStub).vm.$emit('disconnected')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.vnc-stub').exists()).toBe(false)
    expect(wrapper.text()).toContain("Manus Claw's computer is inactive")

    // The component resets vncDisconnected when sessionId changes (e.g.
    // reconnecting to a different/new session) — the documented recovery path.
    await wrapper.setProps({ sessionId: 'sess-2' })
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.vnc-stub').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('computer is inactive')
  })

  it('take control emits ui:takeover with the session id and a Claw-scoped url resolver', async () => {
    const handler = vi.fn()
    eventBus.on('ui:takeover', handler)

    const wrapper = mountContent()
    const takeOverBtn = wrapper.findAll('button').find((b) => b.text().includes('Take control'))
    expect(takeOverBtn).toBeTruthy()
    await takeOverBtn!.trigger('click')

    expect(handler).toHaveBeenCalledTimes(1)
    const payload = handler.mock.calls[0][0]
    expect(payload.sessionId).toBe('sess-1')
    expect(payload.active).toBe(true)
    expect(payload.urlResolver('sess-1')).toBe(getClawVncUrl('sess-1'))
  })

  it('take control does nothing when there is no sessionId (button not even rendered)', () => {
    const handler = vi.fn()
    eventBus.on('ui:takeover', handler)

    const wrapper = mountContent({ sessionId: undefined })

    expect(wrapper.findAll('button').some((b) => b.text().includes('Take control'))).toBe(false)
    expect(handler).not.toHaveBeenCalled()
  })

  it('switches to Agent mode and forwards the raw tool event to ClawAgentTerminalView', async () => {
    const event: ClawEvent = { type: 'tool', phase: 'start', name: 'shell_exec', toolCallId: 'c1' }
    const wrapper = mountContent({ agentToolEvent: event })

    await wrapper.findAll('button').find((b) => b.text() === 'Agent')!.trigger('click')

    const agentStub = wrapper.find('.agent-stub')
    expect(agentStub.exists()).toBe(true)
    expect(JSON.parse(agentStub.text())).toEqual(event)
    expect(wrapper.find('.vnc-stub').exists()).toBe(false)
  })

  it('honors the initialView prop so the panel can land on a non-default tab', () => {
    const wrapper = mountContent({ initialView: 'agent' })

    expect(wrapper.find('.agent-stub').exists()).toBe(true)
    expect(wrapper.find('.vnc-stub').exists()).toBe(false)
  })

  it('defaults to the screen tab when initialView is omitted', () => {
    const wrapper = mountContent()

    expect(wrapper.find('.vnc-stub').exists()).toBe(true)
    expect(wrapper.find('.agent-stub').exists()).toBe(false)
  })

  it('the Close button emits "hide"', async () => {
    const wrapper = mountContent()

    await wrapper.find('[title="Close"]').trigger('click')

    expect(wrapper.emitted('hide')).toHaveLength(1)
  })
})
