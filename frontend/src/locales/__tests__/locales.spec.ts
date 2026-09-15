import { describe, it, expect } from 'vitest'
import en from '../en'
import zh from '../zh'
import pt from '../pt'

describe('locale key parity', () => {
  const enKeys = new Set(Object.keys(en))

  it('zh has no keys missing from en', () => {
    const missing = Object.keys(zh).filter((k) => !enKeys.has(k))
    expect(missing).toEqual([])
  })

  it('pt has no keys missing from en', () => {
    const missing = Object.keys(pt).filter((k) => !enKeys.has(k))
    expect(missing).toEqual([])
  })

  it('every en key exists in zh', () => {
    const zhKeys = new Set(Object.keys(zh))
    const missing = Object.keys(en).filter((k) => !zhKeys.has(k))
    expect(missing).toEqual([])
  })

  it('every en key exists in pt', () => {
    const ptKeys = new Set(Object.keys(pt))
    const missing = Object.keys(en).filter((k) => !ptKeys.has(k))
    expect(missing).toEqual([])
  })
})
