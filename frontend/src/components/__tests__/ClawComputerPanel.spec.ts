import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en'
import ClawComputerPanel from '../ClawComputerPanel.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

// ClawComputerPanelContent mounts ClawTerminalView (real xterm.js); stub it
// out here the same way ComputerToolViews.e2e.spec.ts stubs MonacoEditor —
// this spec is only about ClawComputerPanel's own show/hide/presentation
// plumbing.
const ContentStub = defineComponent({
  name: 'ClawComputerPanelContentStub',
  props: ['presentation', 'sessionId', 'toolLog'],
  emits: ['hide', 'toggle-presentation'],
  setup(props, { emit }) {
    return () => h('div', { class: 'content-stub' }, [
      h('span', { class: 'presentation' }, props.presentation),
      h('button', { class: 'hide-btn', onClick: () => emit('hide') }, 'hide'),
      h('button', { class: 'toggle-btn', onClick: () => emit('toggle-presentation') }, 'toggle'),
    ])
  },
})

beforeAll(() => {
  // useResizeObserver (via ClawComputerPanel's own ref) needs this in jsdom.
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = RO as unknown as typeof ResizeObserver
})

afterEach(() => {
  // attachTo: document.body leaves DOM (including Teleport targets) behind
  // across tests in this file unless explicitly cleared.
  document.body.innerHTML = ''
})

function mountPanel() {
  return mount(ClawComputerPanel, {
    global: {
      plugins: [i18n],
      stubs: { ClawComputerPanelContent: ContentStub },
    },
    props: { sessionId: 'sess-1', toolLog: [] },
    attachTo: document.body,
  })
}

describe('ClawComputerPanel', () => {
  it('is hidden by default and shows the sidebar presentation once showPanel() is called', async () => {
    const wrapper = mountPanel()

    expect(wrapper.vm.isShow).toBe(false)
    expect(wrapper.find('.content-stub').exists()).toBe(false)

    wrapper.vm.showPanel()
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isShow).toBe(true)
    expect(wrapper.find('.content-stub').exists()).toBe(true)
    expect(wrapper.find('.presentation').text()).toBe('sidebar')
  })

  it('hidePanel() hides the panel and resets presentation back to sidebar', async () => {
    const wrapper = mountPanel()

    wrapper.vm.showPanel()
    await wrapper.vm.$nextTick()
    await wrapper.find('.toggle-btn').trigger('click')
    await wrapper.vm.$nextTick()

    // 'dialog' presentation is Teleported to document.body, outside the
    // wrapper's own element subtree — query the document, not the wrapper.
    expect(document.body.querySelector('.presentation')?.textContent).toBe('dialog')

    wrapper.vm.hidePanel()
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isShow).toBe(false)
    expect(document.body.querySelector('.presentation')).toBeNull()

    // Showing it again should be back to sidebar, not the previous dialog mode.
    wrapper.vm.showPanel()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.presentation').text()).toBe('sidebar')
  })

  it('the content stub\'s "hide" event closes the panel', async () => {
    const wrapper = mountPanel()

    wrapper.vm.showPanel()
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.isShow).toBe(true)

    await wrapper.find('.hide-btn').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isShow).toBe(false)
  })

  it('passes sessionId and toolLog through to the content component', async () => {
    const toolLog = [{ id: '1', name: 'shell_exec', argsSummary: '', status: 'running' as const, timestamp: Date.now() }]
    const wrapper = mount(ClawComputerPanel, {
      global: {
        plugins: [i18n],
        stubs: { ClawComputerPanelContent: ContentStub },
      },
      props: { sessionId: 'sess-42', toolLog },
    })

    wrapper.vm.showPanel()
    await wrapper.vm.$nextTick()

    const content = wrapper.findComponent(ContentStub)
    expect(content.props('sessionId')).toBe('sess-42')
    expect(content.props('toolLog')).toEqual(toolLog)
  })
})
