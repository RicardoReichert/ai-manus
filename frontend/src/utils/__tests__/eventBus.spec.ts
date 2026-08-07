import { describe, it, expect, vi } from 'vitest'
import { eventBus } from '../eventBus'

describe('eventBus', () => {
  it('handler receives exact payload passed to emit', () => {
    const handler = vi.fn()
    const payload = {
      message: 'Test message',
      type: 'success' as const,
      duration: 3000
    }

    eventBus.on('ui:toast', handler)
    eventBus.emit('ui:toast', payload)

    expect(handler).toHaveBeenCalledWith(payload)
    expect(handler).toHaveBeenCalledTimes(1)

    eventBus.off('ui:toast', handler)
  })

  it('handler is removed when off is called', () => {
    const handler = vi.fn()
    const payload = {
      message: 'Test message',
      type: 'info' as const,
      duration: 2000
    }

    eventBus.on('ui:toast', handler)
    eventBus.off('ui:toast', handler)
    eventBus.emit('ui:toast', payload)

    expect(handler).not.toHaveBeenCalled()
  })

  it('event with undefined payload can be emitted and received', () => {
    const handler = vi.fn()

    eventBus.on('projects:changed', handler)
    eventBus.emit('projects:changed')

    expect(handler).toHaveBeenCalledWith(undefined)
    expect(handler).toHaveBeenCalledTimes(1)

    eventBus.off('projects:changed', handler)
  })

  it('multiple handlers for same event both fire', () => {
    const handler1 = vi.fn()
    const handler2 = vi.fn()
    const payload = {
      message: 'Test message',
      type: 'error' as const,
      duration: 5000
    }

    eventBus.on('ui:toast', handler1)
    eventBus.on('ui:toast', handler2)
    eventBus.emit('ui:toast', payload)

    expect(handler1).toHaveBeenCalledWith(payload)
    expect(handler1).toHaveBeenCalledTimes(1)
    expect(handler2).toHaveBeenCalledWith(payload)
    expect(handler2).toHaveBeenCalledTimes(1)

    eventBus.off('ui:toast', handler1)
    eventBus.off('ui:toast', handler2)
  })
})
