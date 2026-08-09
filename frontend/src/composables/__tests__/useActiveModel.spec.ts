import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ModelDescriptor } from '../../api/model'

const models: ModelDescriptor[] = [
  { id: 'default', name: 'Default Model', provider: 'openai' },
  { id: 'local-lm', name: 'Local Model', provider: 'openai', is_local: true },
]

const getAvailableModels = vi.fn(async () => models)

vi.mock('../../api/model', () => ({
  getAvailableModels: () => getAvailableModels(),
}))

// The composable holds module-scope state, so each test needs a fresh module
// instance (vi.resetModules) — otherwise selections leak between tests.
async function freshModule() {
  vi.resetModules()
  const mod = await import('../useActiveModel')
  return mod.useActiveModel()
}

describe('useActiveModel', () => {
  beforeEach(() => {
    localStorage.clear()
    getAvailableModels.mockClear()
    getAvailableModels.mockResolvedValue(models)
  })

  it('fetches models once even when called from multiple consumers', async () => {
    const a = await freshModule()
    await Promise.all([a.ensureModelsLoaded(), a.ensureModelsLoaded(), a.ensureModelsLoaded()])
    expect(getAvailableModels).toHaveBeenCalledTimes(1)
    expect(a.availableModels.value).toEqual(models)
  })

  it('defaults to the first registry entry when nothing is saved', async () => {
    const a = await freshModule()
    await a.ensureModelsLoaded()
    expect(a.selectedModelId.value).toBe('default')
    expect(localStorage.getItem('manus_selected_model_id')).toBe('default')
  })

  it('round-trips the selection through a single localStorage key', async () => {
    const a = await freshModule()
    a.setSelectedModel('local-lm')
    expect(localStorage.getItem('manus_selected_model_id')).toBe('local-lm')
    expect(localStorage.getItem('manus_selected_model_name')).toBeNull()
    expect(localStorage.getItem('manus_selected_model_provider')).toBeNull()
  })

  it('falls back to the first entry when the saved id no longer exists', async () => {
    localStorage.setItem('manus_selected_model_id', 'deleted-model')
    const a = await freshModule()
    await a.ensureModelsLoaded()
    expect(a.selectedModelId.value).toBe('default')
  })

  it('isLocalModel reflects the active model', async () => {
    const a = await freshModule()
    await a.ensureModelsLoaded()
    a.setSelectedModel('local-lm')
    expect(a.isLocalModel.value).toBe(true)
    a.setSelectedModel('default')
    expect(a.isLocalModel.value).toBe(false)
  })

  it('hydrateFromSession overrides the persisted selection', async () => {
    const a = await freshModule()
    a.setSelectedModel('default')
    a.hydrateFromSession('local-lm')
    expect(a.selectedModelId.value).toBe('local-lm')
    expect(localStorage.getItem('manus_selected_model_id')).toBe('local-lm')
  })

  it('hydrateFromSession is a no-op for a falsy value', async () => {
    const a = await freshModule()
    a.setSelectedModel('local-lm')
    a.hydrateFromSession(null)
    expect(a.selectedModelId.value).toBe('local-lm')
  })
})
