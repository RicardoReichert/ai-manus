import { describe, it, expect, afterEach, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { i18n } from '../../composables/useI18n'
import { parseISODateTime, formatRelativeTime, formatCustomTime } from '../time'

function withSetup<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({ setup() { result = setup(); return () => null } }),
    { global: { plugins: [i18n] } }
  )
  return { result, wrapper }
}

describe('parseISODateTime', () => {
  it('parses an ISO datetime string into a unix timestamp in seconds', () => {
    const iso = '2025-06-22T04:42:11.842000'
    const expected = new Date(iso).getTime() / 1000 | 0
    expect(parseISODateTime(iso)).toBe(expected)
  })

  it('throws an Error containing "Failed to parse ISO datetime string" for unparseable input', () => {
    expect(() => parseISODateTime('not-a-date')).toThrow('Failed to parse ISO datetime string')
  })
})

describe('formatRelativeTime', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns "Just now" for a timestamp 30s ago', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 30
    const { result } = withSetup(() => formatRelativeTime(timestamp))
    expect(result).toBe('Just now')
  })

  it('returns minutes-ago text for a timestamp 5 minutes ago', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 5 * 60
    const { result } = withSetup(() => formatRelativeTime(timestamp))
    expect(result).toContain('5')
    expect(result).toContain('minutes ago')
  })

  it('returns hours-ago text for a timestamp 3 hours ago', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 3 * 60 * 60
    const { result } = withSetup(() => formatRelativeTime(timestamp))
    expect(result).toContain('3')
    expect(result).toContain('hours ago')
  })

  it('returns days-ago text for a timestamp 10 days ago', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 10 * 24 * 60 * 60
    const { result } = withSetup(() => formatRelativeTime(timestamp))
    expect(result).toContain('10')
    expect(result).toContain('days ago')
  })

  it('returns months-ago text for a timestamp 6 months ago', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 6 * 30 * 24 * 60 * 60
    const { result } = withSetup(() => formatRelativeTime(timestamp))
    expect(result).toContain('6')
    expect(result).toContain('months ago')
  })

  it('returns years-ago text for a timestamp 2 years ago', () => {
    const now = new Date('2026-08-07T12:00:00.000Z')
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000) - 2 * 365 * 24 * 60 * 60
    const { result } = withSetup(() => formatRelativeTime(timestamp))
    expect(result).toContain('2')
    expect(result).toContain('years ago')
  })
})

describe('formatCustomTime', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('formats a timestamp from today as HH:MM 24h time regardless of locale', () => {
    // 2026-08-07 is a Friday
    const now = new Date(2026, 7, 7, 14, 5, 0)
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const timestamp = Math.floor(now.getTime() / 1000)

    const enResult = formatCustomTime(timestamp, undefined, 'en')
    const zhResult = formatCustomTime(timestamp, undefined, 'zh')

    expect(enResult).toMatch(/^\d{2}:\d{2}$/)
    expect(zhResult).toMatch(/^\d{2}:\d{2}$/)
    expect(enResult).toBe(zhResult)
  })

  it('returns the English weekday name for a date within the current week but not today, when no t is passed', () => {
    // 2026-08-07 is a Friday; pick the Tuesday of that same week (2026-08-04)
    const now = new Date(2026, 7, 7, 12, 0, 0)
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const tuesday = new Date(2026, 7, 4, 9, 0, 0)
    const timestamp = Math.floor(tuesday.getTime() / 1000)

    expect(formatCustomTime(timestamp)).toBe('Tuesday')
  })

  it('calls the provided t function with the weekday key for a date within the current week', () => {
    const now = new Date(2026, 7, 7, 12, 0, 0)
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const tuesday = new Date(2026, 7, 4, 9, 0, 0)
    const timestamp = Math.floor(tuesday.getTime() / 1000)

    const t = (k: string) => `T:${k}`
    expect(formatCustomTime(timestamp, t)).toBe('T:Tuesday')
  })

  it('formats a timestamp this year but not this week as MM/DD for both en and zh locales', () => {
    const now = new Date(2026, 7, 7, 12, 0, 0)
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const earlierThisYear = new Date(2026, 0, 15, 9, 0, 0) // Jan 15, 2026
    const timestamp = Math.floor(earlierThisYear.getTime() / 1000)

    expect(formatCustomTime(timestamp, undefined, 'en')).toBe('01/15')
    expect(formatCustomTime(timestamp, undefined, 'zh')).toBe('01/15')
  })

  it('formats a timestamp from a previous year as YYYY/MM', () => {
    const now = new Date(2026, 7, 7, 12, 0, 0)
    vi.useFakeTimers()
    vi.setSystemTime(now)
    const lastYear = new Date(2025, 2, 10, 9, 0, 0) // March 10, 2025
    const timestamp = Math.floor(lastYear.getTime() / 1000)

    expect(formatCustomTime(timestamp)).toBe('2025/03')
  })
})
