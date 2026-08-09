import { describe, it, expect } from 'vitest'
import { cn } from '../utils'

describe('cn', () => {
  it('concatenates multiple string classes', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('dedupes conflicting tailwind utility classes, keeping the last', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })

  it('drops falsy and nullish entries', () => {
    const off: string | false = false
    expect(cn('a', off, undefined, null, 'c')).toBe('a c')
  })

  it('handles object form with boolean values', () => {
    expect(cn({ 'a': true, 'b': false })).toBe('a')
  })
})
