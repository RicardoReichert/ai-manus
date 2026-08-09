import { describe, it, expect, afterEach, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useI18n } from 'vue-i18n'
import { i18n } from '../useI18n'
import { useRelativeTime, useCustomTime } from '../useTime'
import { formatRelativeTime, formatCustomTime } from '../../utils/time'

function withSetup<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({ setup() { result = setup(); return () => null } }),
    { global: { plugins: [i18n] } }
  )
  return { result, wrapper }
}

describe('useRelativeTime', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('relativeTime.value is a function that delegates to formatRelativeTime', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 300

    const { result } = withSetup(() => {
      const { relativeTime } = useRelativeTime()
      expect(typeof relativeTime.value).toBe('function')
      return {
        composableResult: relativeTime.value(timestamp),
        directResult: formatRelativeTime(timestamp)
      }
    })

    expect(result.composableResult).toBe(result.directResult)
  })

  it('recomputes after the 60s interval tick, crossing a "Just now" -> "1 minutes ago" boundary', async () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const mountTimeSec = Math.floor(now.getTime() / 1000)
    // 59s before the original mount time: "Just now" pre-tick, "1 minutes ago" post-tick.
    const fixedTimestamp = mountTimeSec - 59

    const wrapper = mount(
      defineComponent({
        setup() {
          const { relativeTime } = useRelativeTime()
          return () => h('div', relativeTime.value(fixedTimestamp))
        }
      }),
      { global: { plugins: [i18n] } }
    )

    expect(wrapper.text()).toBe('Just now')

    await vi.advanceTimersByTimeAsync(60000)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('minutes ago')

    wrapper.unmount()
  })

  it('clears the interval when the host component unmounts', () => {
    const clearSpy = vi.spyOn(global, 'clearInterval')

    const { wrapper } = withSetup(() => useRelativeTime())
    wrapper.unmount()

    expect(clearSpy).toHaveBeenCalled()
    clearSpy.mockRestore()
  })
})

describe('useCustomTime', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('customTime.value(timestamp) delegates to formatCustomTime(timestamp, t, locale.value)', () => {
    const now = new Date(2026, 7, 7, 14, 5, 0)
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000)

    const { result } = withSetup(() => {
      const { customTime } = useCustomTime()
      const { t, locale } = useI18n()
      expect(typeof customTime.value).toBe('function')
      return {
        composableResult: customTime.value(timestamp),
        directResult: formatCustomTime(timestamp, t, locale.value)
      }
    })

    expect(result.composableResult).toBe(result.directResult)
  })

  it('clears the interval when the host component unmounts', () => {
    const clearSpy = vi.spyOn(global, 'clearInterval')

    const { wrapper } = withSetup(() => useCustomTime())
    wrapper.unmount()

    expect(clearSpy).toHaveBeenCalled()
    clearSpy.mockRestore()
  })
})
