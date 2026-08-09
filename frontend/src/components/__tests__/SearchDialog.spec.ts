import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import SearchDialog from '../SearchDialog.vue'
import { i18n } from '../../composables/useI18n'
import { SessionStatus, type ListSessionItem } from '../../types/response'
import type { SearchResultItem } from '../../api/search'

const searchMessagesMock = vi.fn<(q: string, limit?: number) => Promise<{ results: SearchResultItem[] }>>()
vi.mock('../../api/search', () => ({
  searchMessages: (q: string, limit?: number) => searchMessagesMock(q, limit),
}))

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
})

const sessions: ListSessionItem[] = [
  {
    session_id: 's1',
    title: 'Trip planning',
    latest_message: 'Booked flights',
    latest_message_at: Math.floor(Date.now() / 1000),
    status: SessionStatus.COMPLETED,
    unread_message_count: 0,
    is_shared: false,
    is_favorite: false,
    is_pinned: false,
    is_archived: false,
    project_id: null,
  },
]

const mountDialog = () =>
  mount(SearchDialog, {
    props: { visible: true, sessions },
    global: { plugins: [i18n, router] },
  })

describe('SearchDialog', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    searchMessagesMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows all sessions (browse mode) when the query is blank, without calling search', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(wrapper.text()).toContain('Trip planning')
    expect(searchMessagesMock).not.toHaveBeenCalled()
  })

  it('debounces the search call — no request until 300ms of silence', async () => {
    searchMessagesMock.mockResolvedValue({ results: [] })
    const wrapper = mountDialog()
    await wrapper.find('input').setValue('japan')

    await vi.advanceTimersByTimeAsync(100)
    expect(searchMessagesMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(200)
    expect(searchMessagesMock).toHaveBeenCalledWith('japan', 30)
  })

  it('renders one row per matching message, using the snippet as preview', async () => {
    searchMessagesMock.mockResolvedValue({
      results: [
        { session_id: 's2', session_title: 'Report', snippet: '...quarterly report...', message_at: 1000 },
      ],
    })
    const wrapper = mountDialog()
    await wrapper.find('input').setValue('report')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(wrapper.text()).toContain('Report')
    expect(wrapper.text()).toContain('quarterly report')
    // Browse-mode session shouldn't leak into search results
    expect(wrapper.text()).not.toContain('Trip planning')
  })

  it('a stale response from an earlier keystroke is discarded', async () => {
    let resolveFirst: (v: { results: SearchResultItem[] }) => void
    const firstCall = new Promise<{ results: SearchResultItem[] }>((resolve) => {
      resolveFirst = resolve
    })
    searchMessagesMock
      .mockReturnValueOnce(firstCall)
      .mockResolvedValueOnce({
        results: [{ session_id: 's3', session_title: 'Second', snippet: 'second query hit', message_at: 2000 }],
      })

    const wrapper = mountDialog()
    await wrapper.find('input').setValue('first')
    await vi.advanceTimersByTimeAsync(300)

    await wrapper.find('input').setValue('second')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    // Now resolve the stale first request — it must not overwrite the newer result.
    resolveFirst!({ results: [{ session_id: 's-stale', session_title: 'Stale', snippet: 'stale', message_at: 1 }] })
    await flushPromises()

    expect(wrapper.text()).toContain('Second')
    expect(wrapper.text()).not.toContain('Stale')
  })

  it('shows the empty state once search resolves with no matches', async () => {
    searchMessagesMock.mockResolvedValue({ results: [] })
    const wrapper = mountDialog()
    await wrapper.find('input').setValue('nothingmatchesthis')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(wrapper.text()).toContain('No matching tasks')
  })

  it('clearing the query back to blank returns to browse mode', async () => {
    searchMessagesMock.mockResolvedValue({
      results: [{ session_id: 's2', session_title: 'Report', snippet: 'report', message_at: 1000 }],
    })
    const wrapper = mountDialog()
    const input = wrapper.find('input')
    await input.setValue('report')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(wrapper.text()).toContain('Report')

    await input.setValue('')
    await flushPromises()
    expect(wrapper.text()).toContain('Trip planning')
    expect(wrapper.text()).not.toContain('Report')
  })
})
