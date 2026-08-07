import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import type { FileInfo } from '../../api/file'

// `useMediaQuery` factory has no outer-scope dependency, so no vi.hoisted
// juggling is needed here — we wire up its return value below, after the
// mock is installed.
vi.mock('@vueuse/core', () => ({
  useMediaQuery: vi.fn(),
}))

// The router's `currentRoute` MUST be a genuine Vue `ref`, not a plain
// `{ value }` object: the composable's `canUseSideFilePreview` computed()
// only re-evaluates when it reads a *tracked* reactive dependency. A plain
// object read once during the computed's initial evaluation is never
// registered as a dependency, so the computed caches its first result
// forever and later route reassignments are silently ignored (this bit us
// once already — 8/12 tests failed with stale reads). Building the ref
// inside the async factory (dynamic `import('vue')`) sidesteps needing
// `vi.hoisted` to share an outer-scope `ref` with a hoisted `vi.mock` call.
vi.mock('../../router', async () => {
  const { ref } = await import('vue')
  return {
    router: {
      currentRoute: ref({
        path: '/chat/session-123',
        params: { sessionId: 'session-123' } as Record<string, unknown>,
      }),
    },
  }
})

// Imported after the mocks so useFilePreviewer picks up the mocked deps.
import { useMediaQuery } from '@vueuse/core'
import { router } from '../../router'
import { useFilePreviewer } from '../useFilePreviewer'

// A real ref so mutating `.value` is tracked by the composable's computed.
const mobileRef = ref(false)
vi.mocked(useMediaQuery).mockReturnValue(mobileRef)

const makeFile = (overrides?: Partial<FileInfo>): FileInfo => ({
  file_id: 'f1',
  filename: 'test.txt',
  upload_date: '2026-01-01',
  ...overrides,
})

describe('useFilePreviewer', () => {
  // The module-level `sideGuardStarted`/`isMobileRef` guards mean only this
  // first call wires up the watch/eventBus.on side effects. All tests reuse
  // these same handles (module-scope singleton state) and reset the refs in
  // beforeEach instead of calling useFilePreviewer() again.
  const api = useFilePreviewer()

  beforeEach(() => {
    mobileRef.value = false
    router.currentRoute.value = {
      path: '/chat/session-123',
      params: { sessionId: 'session-123' },
    }
    api.isShow.value = false
    api.fileInfo.value = undefined
    api.viewMode.value = 'center'
    api.fullscreenReturnViewMode.value = 'center'
    api.defaultViewMode.value = 'center'
  })

  describe('canUseSideFilePreview', () => {
    it('is false when route path does not start with /chat/', () => {
      router.currentRoute.value = { path: '/library', params: { sessionId: 'session-123' } }
      expect(api.canUseSideFilePreview.value).toBe(false)
    })

    it("is false when sessionId param is 'claw'", () => {
      router.currentRoute.value = { path: '/chat/claw', params: { sessionId: 'claw' } }
      expect(api.canUseSideFilePreview.value).toBe(false)
    })

    it('is true for a real chat session route when not mobile', () => {
      router.currentRoute.value = {
        path: '/chat/session-123',
        params: { sessionId: 'session-123' },
      }
      mobileRef.value = false
      expect(api.canUseSideFilePreview.value).toBe(true)
    })

    it('is false when mobile, regardless of route', () => {
      router.currentRoute.value = {
        path: '/chat/session-123',
        params: { sessionId: 'session-123' },
      }
      mobileRef.value = true
      expect(api.canUseSideFilePreview.value).toBe(false)
    })
  })

  describe('showFilePreviewer', () => {
    it('sets isShow/fileInfo and defaults to center viewMode', () => {
      const file = makeFile()
      api.showFilePreviewer(file)
      expect(api.isShow.value).toBe(true)
      expect(api.fileInfo.value).toEqual(file)
      expect(api.defaultViewMode.value).toBe('center')
      expect(api.viewMode.value).toBe('center')
    })

    it("resolves 'side' to 'center' when side is unavailable", () => {
      router.currentRoute.value = { path: '/library', params: {} }
      const file = makeFile()
      api.showFilePreviewer(file, 'side')
      expect(api.viewMode.value).toBe('center')
    })

    it("resolves 'side' to 'center' when mobile", () => {
      mobileRef.value = true
      const file = makeFile()
      api.showFilePreviewer(file, 'side')
      expect(api.viewMode.value).toBe('center')
    })
  })

  describe('setViewMode / exitFullscreen', () => {
    it("switching to fullscreen from 'side' records the return mode, exitFullscreen restores it", () => {
      router.currentRoute.value = {
        path: '/chat/session-123',
        params: { sessionId: 'session-123' },
      }
      mobileRef.value = false
      api.setViewMode('side')
      expect(api.viewMode.value).toBe('side')

      api.setViewMode('fullscreen')
      expect(api.fullscreenReturnViewMode.value).toBe('side')
      expect(api.viewMode.value).toBe('fullscreen')

      api.exitFullscreen()
      expect(api.viewMode.value).toBe('side')
    })

    it('exitFullscreen falls back to center if side became unavailable in between', () => {
      router.currentRoute.value = {
        path: '/chat/session-123',
        params: { sessionId: 'session-123' },
      }
      mobileRef.value = false
      api.setViewMode('side')
      api.setViewMode('fullscreen')
      expect(api.fullscreenReturnViewMode.value).toBe('side')

      // side becomes unavailable while in fullscreen
      router.currentRoute.value = { path: '/library', params: {} }

      api.exitFullscreen()
      expect(api.viewMode.value).toBe('center')
    })

    it("setViewMode('side') is a no-op when side is unavailable", () => {
      router.currentRoute.value = { path: '/library', params: {} }
      api.viewMode.value = 'center'
      api.setViewMode('side')
      expect(api.viewMode.value).toBe('center')
    })
  })

  describe('hideFilePreviewer', () => {
    it('hides without touching viewMode', () => {
      api.viewMode.value = 'fullscreen'
      api.isShow.value = true
      api.hideFilePreviewer()
      expect(api.isShow.value).toBe(false)
      expect(api.viewMode.value).toBe('fullscreen')
    })
  })

  describe('setDefaultViewMode', () => {
    it('changes the mode used by a subsequent showFilePreviewer() with no explicit mode', () => {
      api.setDefaultViewMode('fullscreen')
      const file = makeFile()
      api.showFilePreviewer(file)
      expect(api.viewMode.value).toBe('fullscreen')
    })
  })
})
