import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

function withSetup<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setup()
        return () => null
      }
    })
  )
  return { result, wrapper }
}

describe('useI18n (composables/useI18n.ts)', () => {
  const originalLang = document.documentElement.getAttribute('lang')

  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    if (originalLang === null) {
      document.documentElement.removeAttribute('lang')
    } else {
      document.documentElement.setAttribute('lang', originalLang)
    }
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("empty localStorage + navigator.language 'pt-BR' → initial locale 'pt'", async () => {
    localStorage.clear()
    vi.stubGlobal('navigator', { ...navigator, language: 'pt-BR' })

    vi.resetModules()
    const { i18n } = await import('../useI18n')

    expect(i18n.global.locale.value).toBe('pt')
  })

  it("empty localStorage + navigator.language 'zh-CN' → initial locale 'zh'", async () => {
    localStorage.clear()
    vi.stubGlobal('navigator', { ...navigator, language: 'zh-CN' })

    vi.resetModules()
    const { i18n } = await import('../useI18n')

    expect(i18n.global.locale.value).toBe('zh')
  })

  it("empty localStorage + navigator.language 'fr-FR' (unsupported) → falls back to 'en'", async () => {
    localStorage.clear()
    vi.stubGlobal('navigator', { ...navigator, language: 'fr-FR' })

    vi.resetModules()
    const { i18n } = await import('../useI18n')

    expect(i18n.global.locale.value).toBe('en')
  })

  it("stored locale 'zh' wins over navigator.language detection", async () => {
    localStorage.setItem('manus-locale', 'zh')
    vi.stubGlobal('navigator', { ...navigator, language: 'pt-BR' })

    vi.resetModules()
    const { i18n } = await import('../useI18n')

    expect(i18n.global.locale.value).toBe('zh')
  })

  it("useLocale().setLocale('pt') updates i18n locale, currentLocale, localStorage, and <html lang>", async () => {
    vi.resetModules()
    const { i18n, useLocale } = await import('../useI18n')

    const { result } = withSetup(() => useLocale())
    result.setLocale('pt')

    expect(i18n.global.locale.value).toBe('pt')
    expect(result.currentLocale.value).toBe('pt')
    expect(localStorage.getItem('manus-locale')).toBe('pt')
    expect(document.documentElement.getAttribute('lang')).toBe('pt')
  })

  it("changing currentLocale.value directly triggers the watch and applies the same side effects as setLocale", async () => {
    vi.resetModules()
    const { i18n, useLocale } = await import('../useI18n')

    const { result } = withSetup(() => useLocale())
    result.currentLocale.value = 'pt'

    await vi.waitFor(() => {
      expect(i18n.global.locale.value).toBe('pt')
    })
    expect(result.currentLocale.value).toBe('pt')
    expect(localStorage.getItem('manus-locale')).toBe('pt')
    expect(document.documentElement.getAttribute('lang')).toBe('pt')
  })
})
