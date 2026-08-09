import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useResizeObserver } from '../useResizeObserver'

class FakeResizeObserver {
  observe = vi.fn()
  disconnect = vi.fn()
  unobserve = vi.fn()
  constructor(public cb: any) {
    instances.push(this)
  }
}

let instances: FakeResizeObserver[] = []

function withSetup<T>(setup: () => T, template: string) {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setup()
        return result
      },
      template
    })
  )
  return { result, wrapper }
}

describe('useResizeObserver', () => {
  beforeEach(() => {
    instances = []
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("target: 'self', property: 'width' (default) reflects offsetWidth at mount time", async () => {
    const { result, wrapper } = withSetup(() => {
      const el = ref<HTMLElement | null>(null)
      const { size } = useResizeObserver(el, { target: 'self' })
      return { el, size }
    }, '<div ref="el"></div>')

    const el = wrapper.element as HTMLElement
    Object.defineProperty(el, 'offsetWidth', { value: 240, configurable: true })

    await nextTick()
    await nextTick()

    expect(result.size.value).toBe(240)

    wrapper.unmount()
  })

  it("target: 'parent' (default) computes size from the parent of targetRef.value", async () => {
    const { result, wrapper } = withSetup(() => {
      const el = ref<HTMLElement | null>(null)
      const { size } = useResizeObserver(el)
      return { el, size }
    }, '<div><span ref="el"></span></div>')

    const spanEl = wrapper.element.querySelector('span') as HTMLElement
    const parentEl = spanEl.parentElement as HTMLElement
    Object.defineProperty(parentEl, 'offsetWidth', { value: 320, configurable: true })

    await nextTick()
    await nextTick()

    expect(result.size.value).toBe(320)

    wrapper.unmount()
  })

  it("property: 'height' uses offsetHeight instead of offsetWidth", async () => {
    const { result, wrapper } = withSetup(() => {
      const el = ref<HTMLElement | null>(null)
      const { size } = useResizeObserver(el, { target: 'self', property: 'height' })
      return { el, size }
    }, '<div ref="el"></div>')

    const el = wrapper.element as HTMLElement
    Object.defineProperty(el, 'offsetWidth', { value: 999, configurable: true })
    Object.defineProperty(el, 'offsetHeight', { value: 150, configurable: true })

    await nextTick()
    await nextTick()

    expect(result.size.value).toBe(150)

    wrapper.unmount()
  })

  it('invoking the observer callback updates size and calls the optional callback with the new size', async () => {
    const callback = vi.fn()
    const { result, wrapper } = withSetup(() => {
      const el = ref<HTMLElement | null>(null)
      const { size } = useResizeObserver(el, { target: 'self', callback })
      return { el, size }
    }, '<div ref="el"></div>')

    const el = wrapper.element as HTMLElement
    Object.defineProperty(el, 'offsetWidth', { value: 100, configurable: true })

    await nextTick()
    await nextTick()

    expect(result.size.value).toBe(100)
    expect(instances).toHaveLength(1)

    Object.defineProperty(el, 'offsetWidth', { value: 500, configurable: true })
    instances[0].cb()

    expect(result.size.value).toBe(500)
    expect(callback).toHaveBeenCalledWith(500)

    wrapper.unmount()
  })

  it('unmounting the host component calls disconnect() on the fake observer instance', async () => {
    const { wrapper } = withSetup(() => {
      const el = ref<HTMLElement | null>(null)
      const { size } = useResizeObserver(el, { target: 'self' })
      return { el, size }
    }, '<div ref="el"></div>')

    await nextTick()
    await nextTick()

    expect(instances).toHaveLength(1)
    wrapper.unmount()

    expect(instances[0].disconnect).toHaveBeenCalled()
  })

  it('does not throw and keeps size at 0 when targetRef.value is null at mount time', async () => {
    const { result, wrapper } = withSetup(() => {
      const el = ref<HTMLElement | null>(null)
      const { size } = useResizeObserver(el, { target: 'self' })
      return { size }
    }, '<div></div>')

    await expect(
      (async () => {
        await nextTick()
        await nextTick()
      })()
    ).resolves.not.toThrow()

    expect(result.size.value).toBe(0)
    expect(instances).toHaveLength(0)

    wrapper.unmount()
  })
})
