import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en'
import ClawToolDetailView from '../ClawToolDetailView.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

describe('ClawToolDetailView', () => {
  it('shell kind: renders a "$ command" line, output block, and exit code chip', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: {
        name: 'shell_exec',
        args: { command: 'ls -la' },
        result: { exit_code: 0, stdout: 'file1.txt' },
      },
    })

    expect(wrapper.text()).toContain('ls -la')
    expect(wrapper.text()).toContain('Exit code')
    expect(wrapper.text()).toContain('0')
    expect(wrapper.text()).toContain('stdout') // via ClawValueView fallback for non-string result
  })

  it('shell kind: plain string result renders as an Output block, not via ClawValueView', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: { name: 'shell_exec', args: { command: 'echo hi' }, result: 'hi\n' },
    })

    expect(wrapper.text()).toContain('Output')
    expect(wrapper.text()).toContain('hi')
  })

  it('file kind: shows the file path (home prefix stripped) and content preview', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: {
        name: 'file_write',
        args: { path: '/home/ubuntu/notes.txt' },
        result: 'line one\nline two',
      },
    })

    expect(wrapper.text()).toContain('notes.txt')
    expect(wrapper.text()).not.toContain('/home/ubuntu/')
    expect(wrapper.text()).toContain('line one')
  })

  it('browser kind: shows the URL as a chip', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: {
        name: 'browser_navigate',
        args: { url: 'https://example.com' },
        result: { title: 'Example Domain' },
      },
    })

    expect(wrapper.text()).toContain('https://example.com')
    expect(wrapper.text()).toContain('Example Domain')
  })

  it('search kind: shows the query', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: {
        name: 'grep_search',
        args: { query: 'TODO' },
        result: ['file1.ts:12', 'file2.ts:5'],
      },
    })

    expect(wrapper.text()).toContain('TODO')
    expect(wrapper.text()).toContain('file1.ts:12')
  })

  it('generic fallback: unrecognized tool name shows Arguments/Result labels', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: {
        name: 'manus_upload_file',
        args: { file_id: 'abc' },
        result: { uploaded: true },
      },
    })

    expect(wrapper.text()).toContain('Arguments')
    expect(wrapper.text()).toContain('file_id')
    expect(wrapper.text()).toContain('Result')
    expect(wrapper.text()).toContain('uploaded')
  })

  it('generic fallback: labels the result "Error" when isError is true', () => {
    const wrapper = mount(ClawToolDetailView, {
      global: { plugins: [i18n] },
      props: { name: 'manus_upload_file', result: 'boom', isError: true },
    })

    expect(wrapper.text()).toContain('Error')
    expect(wrapper.text()).not.toContain('Result')
  })
})
