import { describe, it, expect, vi } from 'vitest'
import { showToast, showErrorToast, showInfoToast, showSuccessToast } from '../toast'
import { eventBus } from '../eventBus'

describe('toast', () => {
  it('showToast with string emits ui:toast with defaults', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showToast('hello')

    expect(handler).toHaveBeenCalledWith({
      message: 'hello',
      type: 'info',
      duration: 3000
    })
    expect(handler).toHaveBeenCalledTimes(1)

    eventBus.off('ui:toast', handler)
  })

  it('showToast with object emits with all fields passed through', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showToast({ message: 'x', type: 'error', duration: 500 })

    expect(handler).toHaveBeenCalledWith({
      message: 'x',
      type: 'error',
      duration: 500
    })
    expect(handler).toHaveBeenCalledTimes(1)

    eventBus.off('ui:toast', handler)
  })

  it('showToast with object missing type and duration uses defaults', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showToast({ message: 'x' })

    expect(handler).toHaveBeenCalledWith({
      message: 'x',
      type: 'info',
      duration: 3000
    })
    expect(handler).toHaveBeenCalledTimes(1)

    eventBus.off('ui:toast', handler)
  })

  it('showToast preserves duration 0 as 0, not overridden by default', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showToast({ message: 'x', duration: 0 })

    expect(handler).toHaveBeenCalledWith({
      message: 'x',
      type: 'info',
      duration: 0
    })
    expect(handler).toHaveBeenCalledTimes(1)

    eventBus.off('ui:toast', handler)
  })

  it('showErrorToast emits with type error', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showErrorToast('x')

    expect(handler).toHaveBeenCalledWith({
      message: 'x',
      type: 'error',
      duration: 3000
    })

    eventBus.off('ui:toast', handler)
  })

  it('showInfoToast emits with type info', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showInfoToast('x')

    expect(handler).toHaveBeenCalledWith({
      message: 'x',
      type: 'info',
      duration: 3000
    })

    eventBus.off('ui:toast', handler)
  })

  it('showSuccessToast emits with type success', () => {
    const handler = vi.fn()
    eventBus.on('ui:toast', handler)

    showSuccessToast('x')

    expect(handler).toHaveBeenCalledWith({
      message: 'x',
      type: 'success',
      duration: 3000
    })

    eventBus.off('ui:toast', handler)
  })

  it('window.toast.show is showToast', () => {
    expect(window.toast.show).toBe(showToast)
  })

  it('window.toast.error is showErrorToast', () => {
    expect(window.toast.error).toBe(showErrorToast)
  })

  it('window.toast.info is showInfoToast', () => {
    expect(window.toast.info).toBe(showInfoToast)
  })

  it('window.toast.success is showSuccessToast', () => {
    expect(window.toast.success).toBe(showSuccessToast)
  })
})
