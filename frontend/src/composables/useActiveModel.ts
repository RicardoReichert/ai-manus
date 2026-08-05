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

async function ensureModelsLoaded(): Promise<void> {
  if (availableModels.value.length > 0) return
  if (!loadPromise) {
    loadPromise = getAvailableModels()
      .then((models) => {
        availableModels.value = models
        // A saved id that no longer exists in the registry falls back to the
        // first entry, which is always the configured default (see backend
        // model_registry._default_model).
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
    setSelectedModel,
    hydrateFromSession,
  }
}
