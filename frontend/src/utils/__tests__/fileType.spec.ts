import { describe, it, expect } from 'vitest'
import { formatFileSize } from '../fileType'

describe('formatFileSize', () => {
  it('formats a real zero-byte file as 0 B', () => {
    expect(formatFileSize(0)).toBe('0 B')
  })

  it('returns empty string for undefined (unknown size, not zero)', () => {
    expect(formatFileSize(undefined)).toBe('')
  })

  it('returns empty string for null (unknown size, not zero)', () => {
    expect(formatFileSize(null)).toBe('')
  })

  it('formats bytes below 1KB', () => {
    expect(formatFileSize(500)).toBe('500 B')
  })

  it('formats kilobytes', () => {
    expect(formatFileSize(1024)).toBe('1 KB')
  })

  it('formats megabytes', () => {
    expect(formatFileSize(33830536)).toBe('32.3 MB')
  })
})
