import { describe, it, expect } from 'vitest'
import { formatDuration } from '../duration'

describe('formatDuration', () => {
  it('formats 0ms as 0:00', () => {
    expect(formatDuration(0)).toBe('0:00')
  })

  it('formats sub-second durations as 0:00', () => {
    expect(formatDuration(400)).toBe('0:00')
  })

  it('formats 59s as 0:59', () => {
    expect(formatDuration(59_000)).toBe('0:59')
  })

  it('formats 60s as 1:00', () => {
    expect(formatDuration(60_000)).toBe('1:00')
  })

  it('formats 61s as 1:01', () => {
    expect(formatDuration(61_000)).toBe('1:01')
  })

  it('formats past an hour as h:mm:ss', () => {
    expect(formatDuration(3661_000)).toBe('1:01:01')
  })

  it('returns empty string for undefined', () => {
    expect(formatDuration(undefined)).toBe('')
  })

  it('returns empty string for null', () => {
    expect(formatDuration(null)).toBe('')
  })

  it('returns empty string for negative values', () => {
    expect(formatDuration(-500)).toBe('')
  })
})
