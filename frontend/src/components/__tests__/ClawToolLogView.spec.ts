import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en'
import ClawToolLogView from '../ClawToolLogView.vue'
import type { ClawToolLogEntry } from '@/api/claw'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

function entry(partial: Partial<ClawToolLogEntry>): ClawToolLogEntry {
  return {
    id: 'call-1',
    name: 'shell_exec',
    argsSummary: '',
    status: 'running',
    timestamp: Date.now(),
    ...partial,
  }
}

describe('ClawToolLogView', () => {
  it('shows the empty state when there is no tool activity yet', () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: { toolLog: [] },
    })

    expect(wrapper.text()).toContain('No tool activity yet')
  })

  it('defaults toolLog to an empty list (empty state) when the prop is omitted', () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
    })

    expect(wrapper.text()).toContain('No tool activity yet')
  })

  it('renders one row per log entry with name, status label, and arg summary', () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [
          entry({ id: 'a', name: 'shell_exec', status: 'running', argsSummary: 'ls -la' }),
          entry({ id: 'b', name: 'file_write', status: 'success' }),
          entry({ id: 'c', name: 'browser_navigate', status: 'error' }),
        ],
      },
    })

    expect(wrapper.text()).not.toContain('No tool activity yet')
    expect(wrapper.text()).toContain('shell_exec')
    expect(wrapper.text()).toContain('Running')
    expect(wrapper.text()).toContain('ls -la')
    expect(wrapper.text()).toContain('file_write')
    expect(wrapper.text()).toContain('Done')
    expect(wrapper.text()).toContain('browser_navigate')
    expect(wrapper.text()).toContain('Error')
  })

  it('does not render an arg-summary line when argsSummary is absent', () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: { toolLog: [entry({ id: 'a', name: 'shell_exec' })] },
    })

    // Only the name/status row exists; no secondary summary div was rendered.
    const rows = wrapper.findAll('.rounded-\\[8px\\]')
    expect(rows).toHaveLength(1)
    expect(rows[0].findAll('div').some((d) => d.classes().includes('text-[var(--text-secondary)]'))).toBe(false)
  })

  it('entries without args/result render no chevron and cannot be expanded', () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: { toolLog: [entry({ id: 'a' })] },
    })

    expect(wrapper.find('[role="button"]').attributes('tabindex')).toBe('-1')
    expect(wrapper.text()).not.toContain('Arguments')
    expect(wrapper.text()).not.toContain('Result')
  })

  it('clicking a row with details expands its detail view, collapsed by default', async () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [entry({
          id: 'a',
          name: 'custom_tool_xyz', // unrecognized name -> generic kind (Arguments/Result labels)
          status: 'success',
          args: { command: 'ls -la' },
          result: 'file1.txt\nfile2.txt',
        })],
      },
    })

    // Collapsed by default.
    expect(wrapper.text()).not.toContain('file1.txt')
    expect(wrapper.find('[role="button"]').attributes('aria-expanded')).toBe('false')

    await wrapper.find('[role="button"]').trigger('click')

    expect(wrapper.find('[role="button"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.text()).toContain('Arguments')
    expect(wrapper.text()).toContain('ls -la')
    expect(wrapper.text()).toContain('Result')
    expect(wrapper.text()).toContain('file1.txt')

    // Clicking again collapses it back.
    await wrapper.find('[role="button"]').trigger('click')
    expect(wrapper.text()).not.toContain('file1.txt')
  })

  it('renders a shell-kind entry as a command line + output, not generic Arguments/Result', async () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [entry({
          id: 'a',
          name: 'shell_exec',
          status: 'success',
          args: { command: 'ls -la' },
          result: 'file1.txt',
        })],
      },
    })

    await wrapper.find('[role="button"]').trigger('click')

    expect(wrapper.text()).toContain('ls -la')
    expect(wrapper.text()).toContain('file1.txt')
    expect(wrapper.text()).not.toContain('Arguments')
  })

  it('shows a truncation notice when the entry is marked truncated', async () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [entry({ id: 'a', result: 'partial output...', truncated: true })],
      },
    })

    await wrapper.find('[role="button"]').trigger('click')

    expect(wrapper.text()).toContain('Output truncated')
  })

  it('labels the result section "Error" (not "Result") and colors it for an errored entry', async () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [entry({ id: 'a', status: 'error', result: 'boom: command failed' })],
      },
    })

    await wrapper.find('[role="button"]').trigger('click')

    expect(wrapper.text()).toContain('Error')
    expect(wrapper.text()).not.toContain('Result')
    expect(wrapper.text()).toContain('boom: command failed')
  })

  it('renders an object result as key/value rows, not a raw JSON string', async () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [entry({
          id: 'a',
          status: 'success',
          result: { exit_code: 0, stdout: 'ok', nested: { bytes: 12 } },
        })],
      },
    })

    await wrapper.find('[role="button"]').trigger('click')

    // Key labels rendered individually (structured rows), not as JSON syntax.
    expect(wrapper.text()).toContain('exit_code')
    expect(wrapper.text()).toContain('stdout')
    expect(wrapper.text()).toContain('ok')
    expect(wrapper.text()).toContain('nested')
    expect(wrapper.text()).toContain('bytes')
    expect(wrapper.text()).not.toContain('{"exit_code"')
    expect(wrapper.text()).not.toContain('{\n')
  })

  it('maps status to the expected dot color class', () => {
    const wrapper = mount(ClawToolLogView, {
      global: { plugins: [i18n] },
      props: {
        toolLog: [
          entry({ id: 'a', status: 'running' }),
          entry({ id: 'b', status: 'success' }),
          entry({ id: 'c', status: 'error' }),
        ],
      },
    })

    const dots = wrapper.findAll('span.h-\\[6px\\]')
    expect(dots).toHaveLength(3)
    expect(dots[0].classes()).toContain('bg-[var(--function-warning)]')
    expect(dots[0].classes()).toContain('animate-pulse')
    expect(dots[1].classes()).toContain('bg-[var(--function-success)]')
    expect(dots[2].classes()).toContain('bg-[var(--function-error)]')
  })
})
