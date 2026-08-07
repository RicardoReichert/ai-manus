import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getParentElement, copyToClipboard } from '../dom'

describe('getParentElement', () => {
  beforeEach(() => {
    // Set up DOM structure for testing
    document.body.innerHTML = `
      <div id="grandparent" class="container">
        <div id="parent" class="wrapper">
          <div id="child" class="content">
            <span id="target">Text</span>
          </div>
        </div>
      </div>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('returns parentElement when given a CSS selector string', () => {
    const parent = getParentElement('#target')
    expect(parent).toBe(document.getElementById('child'))
  })

  it('returns parentElement when given an HTMLElement reference directly', () => {
    const target = document.getElementById('target')!
    const parent = getParentElement(target)
    expect(parent).toBe(document.getElementById('child'))
  })

  it('returns parentElement when given an Element reference', () => {
    const target = document.querySelector('#target')!
    const parent = getParentElement(target)
    expect(parent).toBe(document.getElementById('child'))
  })

  it('returns element.closest(parentSelector) when parentSelector is provided', () => {
    const ancestor = getParentElement('#target', '.container')
    expect(ancestor).toBe(document.getElementById('grandparent'))
  })

  it('returns the closest matching ancestor with parentSelector', () => {
    const ancestor = getParentElement('#target', '.wrapper')
    expect(ancestor).toBe(document.getElementById('parent'))
  })

  it('returns null when the selector matches nothing', () => {
    const result = getParentElement('#nonexistent')
    expect(result).toBeNull()
  })

  it('returns null when parentSelector finds no ancestor', () => {
    const result = getParentElement('#target', '.nonexistent-class')
    expect(result).toBeNull()
  })

  it('returns null when HTMLElement has no parent', () => {
    const orphan = document.createElement('div')
    const result = getParentElement(orphan)
    expect(result).toBeNull()
  })
})

describe('copyToClipboard', () => {
  beforeEach(() => {
    // Reset document.execCommand mock for each test
    const execCommandMock = vi.fn().mockReturnValue(false)
    Object.defineProperty(document, 'execCommand', {
      value: execCommandMock,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses navigator.clipboard.writeText when available and resolves', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
    })

    const result = await copyToClipboard('test text')

    expect(result).toBe(true)
    expect(writeTextMock).toHaveBeenCalledWith('test text')
  })

  it('falls back to document.execCommand when navigator.clipboard.writeText rejects', async () => {
    const writeTextMock = vi.fn().mockRejectedValue(new Error('Clipboard API failed'))
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
    })

    const execCommandMock = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, 'execCommand', {
      value: execCommandMock,
      writable: true,
      configurable: true,
    })

    const result = await copyToClipboard('test text')

    expect(result).toBe(true)
    expect(writeTextMock).toHaveBeenCalledWith('test text')
    expect(execCommandMock).toHaveBeenCalledWith('copy')
  })

  it('uses fallback textarea method when navigator.clipboard is absent', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    })

    const execCommandMock = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, 'execCommand', {
      value: execCommandMock,
      writable: true,
      configurable: true,
    })

    const result = await copyToClipboard('test text')

    expect(result).toBe(true)
    expect(execCommandMock).toHaveBeenCalledWith('copy')
  })

  it('returns false when fallback document.execCommand returns false', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    })

    const execCommandMock = vi.fn().mockReturnValue(false)
    Object.defineProperty(document, 'execCommand', {
      value: execCommandMock,
      writable: true,
      configurable: true,
    })

    const result = await copyToClipboard('test text')

    expect(result).toBe(false)
    expect(execCommandMock).toHaveBeenCalledWith('copy')
  })

  it('returns false when fallback document.execCommand throws', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    })

    const execCommandMock = vi.fn().mockImplementation(() => {
      throw new Error('execCommand failed')
    })
    Object.defineProperty(document, 'execCommand', {
      value: execCommandMock,
      writable: true,
      configurable: true,
    })

    const result = await copyToClipboard('test text')

    expect(result).toBe(false)
    expect(execCommandMock).toHaveBeenCalledWith('copy')
  })

  it('restores focus to the previous active element after copying', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    })

    const execCommandMock = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, 'execCommand', {
      value: execCommandMock,
      writable: true,
      configurable: true,
    })

    // Create a mock element and set it as active
    const focusedElement = document.createElement('button')
    focusedElement.focus()
    const focusSpy = vi.spyOn(focusedElement, 'focus')

    // Mock document.activeElement to return our focused element
    Object.defineProperty(document, 'activeElement', {
      value: focusedElement,
      configurable: true,
    })

    await copyToClipboard('test text')

    expect(focusSpy).toHaveBeenCalled()
  })
})
