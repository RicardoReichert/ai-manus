// Single source of truth for the selected LLM model. Module-scope state
// (matching useSessionFileList / useFilePreviewer) so ModelSelectorDropdown,
// ChatPage, HomePage, the chat model badge, and the task logs drawer all
// read/write the same values instead of maintaining separate copies.
import { computed, ref } from 'vue'
import { getAvailableModels, type ModelDescriptor } from '../api/model'

const STORAGE_KEY = 'manus_selected_model_id'

const availableModels = ref<ModelDescriptor[]>([])
const selectedModelId = ref<string | null>(localStorage.getItem(STORAGE_KEY))

let loadPromise: Promise<void> | null = null

async function doLoad(): Promise<void> {
  if (!loadPromise) {
    loadPromise = getAvailableModels()
      .then((models) => {
        availableModels.value = models
        // A saved id that no longer exists in the registry falls back to the
        // first entry, which is always the configured default (see backend
        // model_registry.get_default_model). Without this, a model deleted
        // or renamed by an admin after this id was cached would make every
        // session-creation request 400 with "Unknown model" — silently, from
        // the user's side, since they never touched the dropdown.
        if (
          models.length > 0 &&
          (!selectedModelId.value || !models.some((m) => m.id === selectedModelId.value))
        ) {
          setSelectedModel(models[0].id)
        }
      })
      .catch((e) => {
        console.warn('Failed to load available models:', e)
      })
      .finally(() => {
        loadPromise = null
      })
  }
  return loadPromise
}

/** Load the registry once; cheap to call repeatedly (e.g. on every mount). */
async function ensureModelsLoaded(): Promise<void> {
  if (availableModels.value.length > 0) return
  return doLoad()
}

/**
 * Force a fresh read of the registry, e.g. after an admin adds/edits/removes
 * a model in Settings > Models, or right before creating a session so a
 * stale cached id (deleted or disabled since it was last selected) can never
 * make session creation fail. Cheap: a single GET against a 30s-cached
 * backend endpoint, not a page reload.
 */
async function refreshModels(): Promise<void> {
  return doLoad()
}

function setSelectedModel(id: string): void {
  selectedModelId.value = id
  localStorage.setItem(STORAGE_KEY, id)
}

/** Restore the model persisted on a session, e.g. after loading /chat/:id. */
function hydrateFromSession(modelName?: string | null): void {
  if (modelName) {
    setSelectedModel(modelName)
  }
}

const activeModel = computed<ModelDescriptor | undefined>(() =>
  availableModels.value.find((m) => m.id === selectedModelId.value) ?? availableModels.value[0]
)

const activeModelName = computed(() => activeModel.value?.name)
const isLocalModel = computed(() => activeModel.value?.is_local ?? false)

export function useActiveModel() {
  return {
    availableModels,
    selectedModelId,
    activeModel,
    activeModelName,
    isLocalModel,
    ensureModelsLoaded,
    refreshModels,
    setSelectedModel,
    hydrateFromSession,
  }
}
