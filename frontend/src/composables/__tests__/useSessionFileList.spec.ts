import { describe, it, expect } from 'vitest'
import { useSessionFileList } from '../useSessionFileList'

describe('useSessionFileList', () => {
  it('default state: visible and shared are false', () => {
    const { visible, shared } = useSessionFileList()
    expect(visible.value).toBe(false)
    expect(shared.value).toBe(false)
  })

  it('showSessionFileList() with no arg sets visible to true and shared to false', () => {
    const { visible, shared, showSessionFileList } = useSessionFileList()
    showSessionFileList()
    expect(visible.value).toBe(true)
    expect(shared.value).toBe(false)
  })

  it('showSessionFileList(true) sets visible and shared to true', () => {
    const { visible, shared, showSessionFileList } = useSessionFileList()
    showSessionFileList(true)
    expect(visible.value).toBe(true)
    expect(shared.value).toBe(true)
  })

  it('hideSessionFileList() sets visible to false without resetting shared', () => {
    const { visible, shared, showSessionFileList, hideSessionFileList } = useSessionFileList()
    showSessionFileList(true)
    expect(visible.value).toBe(true)
    expect(shared.value).toBe(true)
    hideSessionFileList()
    expect(visible.value).toBe(false)
    expect(shared.value).toBe(true)
  })
})
