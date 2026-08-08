import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ClawValueView from '../ClawValueView.vue'

describe('ClawValueView', () => {
  it('renders a plain object as key/value rows', () => {
    const wrapper = mount(ClawValueView, { props: { value: { exit_code: 0, stdout: 'ok' } } })

    expect(wrapper.text()).toContain('exit_code')
    expect(wrapper.text()).toContain('0')
    expect(wrapper.text()).toContain('stdout')
    expect(wrapper.text()).toContain('ok')
    // Not rendered as a JSON blob.
    expect(wrapper.text()).not.toMatch(/[{}]/)
  })

  it('renders nested objects recursively, indented under their key', () => {
    const wrapper = mount(ClawValueView, {
      props: { value: { outer: { inner: 'deep value' } } },
    })

    expect(wrapper.text()).toContain('outer')
    expect(wrapper.text()).toContain('inner')
    expect(wrapper.text()).toContain('deep value')
  })

  it('renders arrays as numbered rows', () => {
    const wrapper = mount(ClawValueView, { props: { value: ['a', 'b', 'c'] } })

    expect(wrapper.text()).toContain('#1')
    expect(wrapper.text()).toContain('a')
    expect(wrapper.text()).toContain('#2')
    expect(wrapper.text()).toContain('b')
    expect(wrapper.text()).toContain('#3')
    expect(wrapper.text()).toContain('c')
  })

  it('renders a plain string result as-is (preserving newlines via CSS), not as a JSON string literal', () => {
    const wrapper = mount(ClawValueView, { props: { value: 'line1\nline2' } })

    expect(wrapper.html()).toContain('line1\nline2')
    expect(wrapper.html()).not.toContain('"line1')
  })

  it('renders null and booleans as readable text, not JS defaults', () => {
    const wrapper = mount(ClawValueView, {
      props: { value: { a: null, b: true, c: false, d: 42 } },
    })

    expect(wrapper.text()).toContain('null')
    expect(wrapper.text()).toContain('true')
    expect(wrapper.text()).toContain('false')
    expect(wrapper.text()).toContain('42')
  })

  it('falls back to compact JSON only past maxDepth, to bound recursion', () => {
    const value = { l1: { l2: { l3: { l4: { l5: 'too deep' } } } } }
    const wrapper = mount(ClawValueView, { props: { value, maxDepth: 2 } })

    // Levels within maxDepth still render as structured rows.
    expect(wrapper.text()).toContain('l1')
    expect(wrapper.text()).toContain('l2')
    // Beyond maxDepth, falls back to a compact inline JSON string rather
    // than an unbounded recursive tree.
    expect(wrapper.text()).toContain('"l4"')
  })
})
