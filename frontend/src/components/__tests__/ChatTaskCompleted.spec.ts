import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatTaskCompleted from '../ChatTaskCompleted.vue'
import { i18n } from '../../composables/useI18n'

describe('ChatTaskCompleted follow-up suggestions (5.2)', () => {
  it('renders nothing when not visible', () => {
    const wrapper = mount(ChatTaskCompleted, {
      props: { visible: false, copyText: '', followUps: ['Add a chart'] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('renders no chips when follow-ups is empty', () => {
    const wrapper = mount(ChatTaskCompleted, {
      props: { visible: true, copyText: 'done', followUps: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('[data-testid="follow-up-chip"]').length).toBe(0)
  })

  it('renders no chips when follow-ups is null/undefined', () => {
    const wrapper = mount(ChatTaskCompleted, {
      props: { visible: true, copyText: 'done', followUps: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('[data-testid="follow-up-chip"]').length).toBe(0)
  })

  it('renders a chip per suggestion and filters out blank ones', () => {
    const wrapper = mount(ChatTaskCompleted, {
      props: {
        visible: true,
        copyText: 'done',
        followUps: ['Add a chart', '   ', 'Deploy it'],
      },
      global: { plugins: [i18n] },
    })
    const chips = wrapper.findAll('[data-testid="follow-up-chip"]')
    expect(chips.map((b) => b.text())).toEqual(['Add a chart', 'Deploy it'])
  })

  it('emits followUp with the suggestion text on click', async () => {
    const wrapper = mount(ChatTaskCompleted, {
      props: { visible: true, copyText: 'done', followUps: ['Add a chart'] },
      global: { plugins: [i18n] },
    })
    await wrapper.find('[data-testid="follow-up-chip"]').trigger('click')
    expect(wrapper.emitted('followUp')).toEqual([['Add a chart']])
  })
})
