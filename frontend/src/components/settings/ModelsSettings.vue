<template>
  <div class="space-y-6 w-full">
    <div class="flex items-start justify-between gap-4">
      <p class="text-[13px] text-[var(--text-tertiary)] leading-[18px] flex-1">
        {{ t('Models registered here appear in the chat and Manus Claw model dropdowns for every user. Credentials are encrypted and never shown again after saving.') }}
      </p>
      <button
        type="button"
        class="h-9 px-3.5 rounded-[10px] bg-[var(--Button-black)] text-[var(--text-onblack)] text-sm font-medium clickable hover:opacity-90 flex-shrink-0"
        @click="openCreateForm"
      >
        {{ t('Add model') }}
      </button>
    </div>

    <div v-if="encryptionWarning" class="rounded-[10px] px-3.5 py-3 text-[13px] leading-[18px] bg-[var(--fill-red-light)] text-[var(--text-red)] border border-[var(--border-red)]">
      {{ t('MODEL_ENCRYPTION_KEY is not configured on the server, so models with an API key cannot be saved. Local models with no credential (LM Studio, Ollama) are unaffected.') }}
    </div>

    <div v-if="isLoading" class="py-10 text-center text-sm text-[var(--text-tertiary)]">
      {{ t('Loading...') }}
    </div>

    <div v-else-if="models.length === 0" class="py-10 text-center text-sm text-[var(--text-tertiary)]">
      {{ t('No models configured — add the first one.') }}
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="m in models"
        :key="m.id"
        class="rounded-[12px] border border-[var(--border-main)] p-3.5 space-y-2"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm font-medium text-[var(--text-primary)] truncate">{{ m.name }}</span>
              <span class="text-[11px] px-1.5 py-0.5 rounded bg-[var(--fill-tsp-white-main)] text-[var(--text-tertiary)]">{{ m.provider }}</span>
              <span v-if="m.is_local" class="text-[10px] font-semibold text-blue-500 bg-blue-500/10 px-1.5 py-0.5 rounded">{{ t('Local') }}</span>
              <span v-if="!m.enabled" class="text-[10px] font-semibold text-[var(--text-tertiary)] bg-[var(--fill-tsp-white-main)] px-1.5 py-0.5 rounded">{{ t('Disabled') }}</span>
              <span v-if="m.capabilities.max_tools" class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600" :title="t('Tool count is limited for this model, and browsing is delegated to a sub-agent.')">
                {{ t('Small-model profile') }}
              </span>
            </div>
            <p class="text-[12px] text-[var(--text-tertiary)] truncate mt-0.5">{{ m.model }}</p>
          </div>
          <div class="flex items-center gap-1.5 flex-shrink-0">
            <button
              type="button"
              class="h-7 px-2.5 rounded-[8px] text-[12px] font-medium clickable hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)]"
              :disabled="testingId === m.id"
              @click="handleTest(m)"
            >
              {{ testingId === m.id ? t('Testing...') : t('Test connection') }}
            </button>
            <button
              type="button"
              class="h-7 px-2.5 rounded-[8px] text-[12px] font-medium clickable hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)]"
              @click="openEditForm(m)"
            >
              {{ t('Edit') }}
            </button>
            <button
              type="button"
              class="h-7 px-2.5 rounded-[8px] text-[12px] font-medium clickable hover:bg-red-500/10 text-red-500"
              @click="handleDelete(m)"
            >
              {{ t('Delete') }}
            </button>
          </div>
        </div>

        <p v-if="testResults[m.id]" class="text-[12px]" :class="testResults[m.id]!.ok ? 'text-green-600' : 'text-red-500'">
          {{ testResults[m.id]!.ok
            ? t('Connected ({ms} ms)', { ms: testResults[m.id]!.latency_ms ?? 0 })
            : testResults[m.id]!.error }}
        </p>
      </div>
    </div>

    <!-- Create / edit form -->
    <div v-if="formOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4" @click.self="closeForm">
      <div class="w-full max-w-[480px] max-h-[85vh] overflow-y-auto rounded-[16px] bg-[var(--background-menu-white)] border border-[var(--border-light)] p-5 space-y-4 shadow-menu">
        <h3 class="text-[16px] font-medium text-[var(--text-primary)]">
          {{ editingId ? t('Edit model') : t('Add model') }}
        </h3>

        <div v-if="!editingId" class="space-y-2">
          <p class="text-[13px] text-[var(--text-secondary)]">{{ t('Provider') }}</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="preset in MODEL_PROVIDER_PRESETS"
              :key="preset.id"
              type="button"
              class="h-8 px-3 rounded-[8px] text-[13px] font-medium clickable border"
              :class="selectedPresetId === preset.id
                ? 'border-[var(--Button-black)] text-[var(--text-primary)]'
                : 'border-[var(--Button-border-secondary)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-light)]'"
              @click="applyPreset(preset)"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>

        <FormField :label="t('Display name')">
          <input v-model="form.name" class="settings-input" :placeholder="t('e.g. GPT-4o')" />
        </FormField>

        <FormField v-if="!editingId" :label="t('Registry ID')" :hint="t('Used internally; cannot be changed after creation.')">
          <input v-model="form.id" class="settings-input" placeholder="my-gpt-4o" />
        </FormField>

        <FormField :label="t('Model name')" :hint="t('The exact name the provider expects.')">
          <input v-model="form.model" class="settings-input" :placeholder="currentPreset?.modelPlaceholder || 'model-name'" />
        </FormField>

        <FormField :label="t('Base URL')" :hint="t('Leave empty for the provider default.')">
          <input v-model="form.base_url" class="settings-input" placeholder="https://..." />
        </FormField>

        <FormField :label="t('API key')" :hint="apiKeyHint">
          <input v-model="form.api_key" type="password" class="settings-input" :placeholder="apiKeyPlaceholder" />
        </FormField>

        <FormField :label="t('Tool profile')" :hint="t('Lean gives the model shell/file/message/search plus delegated browsing — best for small (~4B) models.')">
          <div class="flex gap-1.5">
            <button
              v-for="profile in (['full', 'lean'] as const)"
              :key="profile"
              type="button"
              class="h-8 px-3 rounded-[8px] text-[13px] font-medium clickable border"
              :class="form.tool_profile === profile
                ? 'border-[var(--Button-black)] text-[var(--text-primary)]'
                : 'border-[var(--Button-border-secondary)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-light)]'"
              @click="form.tool_profile = profile"
            >
              {{ profile === 'full' ? t('Full') : t('Lean') }}
            </button>
          </div>
        </FormField>

        <label class="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer">
          <input v-model="form.enabled" type="checkbox" class="rounded" />
          {{ t('Enabled (visible in the model dropdown)') }}
        </label>

        <div v-if="editingId" class="flex items-center justify-between">
          <label class="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer">
            <input v-model="form.clear_api_key" type="checkbox" class="rounded" />
            {{ t('Remove stored API key') }}
          </label>
        </div>

        <div v-if="formError" class="text-[13px] text-red-500">{{ formError }}</div>

        <div class="flex items-center justify-end gap-2 pt-2">
          <button type="button" class="h-9 px-3.5 rounded-[10px] text-sm font-medium clickable hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)]" @click="closeForm">
            {{ t('Cancel') }}
          </button>
          <button
            type="button"
            class="h-9 px-3.5 rounded-[10px] bg-[var(--Button-black)] text-[var(--text-onblack)] text-sm font-medium clickable hover:opacity-90 disabled:opacity-50"
            :disabled="isSaving || !form.name || (!editingId && !form.id) || !form.model"
            @click="handleSave"
          >
            {{ isSaving ? t('Saving...') : t('Save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  listModelConfigs, createModelConfig, updateModelConfig, deleteModelConfig, testModelConnection,
  MODEL_PROVIDER_PRESETS, type ModelConfigEntry, type ModelProviderPreset, type ToolProfile,
  type TestConnectionResult,
} from '@/api/modelConfig'
import { useDialog } from '@/composables/useDialog'
import { showSuccessToast, showErrorToast } from '@/utils/toast'

const { t } = useI18n()
const { showConfirmDialog } = useDialog()

// Small inline field wrapper — kept local since it's only used in this form.
const FormField = (props: { label: string; hint?: string }, { slots }: any) =>
  h('div', { class: 'space-y-1.5' }, [
    h('p', { class: 'text-[13px] text-[var(--text-secondary)]' }, props.label),
    slots.default?.(),
    props.hint ? h('p', { class: 'text-[11px] text-[var(--text-tertiary)]' }, props.hint) : null,
  ])

const models = ref<ModelConfigEntry[]>([])
const isLoading = ref(true)
const encryptionWarning = ref(false)
const testingId = ref<string | null>(null)
const testResults = reactive<Record<string, TestConnectionResult>>({})

const formOpen = ref(false)
const editingId = ref<string | null>(null)
const isSaving = ref(false)
const formError = ref('')
const selectedPresetId = ref<string>('openai')

const form = reactive({
  id: '',
  name: '',
  model: '',
  base_url: '',
  api_key: '',
  clear_api_key: false,
  enabled: true,
  is_local: false,
  provider: 'openai',
  tool_profile: 'full' as ToolProfile,
})

const currentPreset = computed(() => MODEL_PROVIDER_PRESETS.find((p) => p.id === selectedPresetId.value))

const editingModel = computed(() => models.value.find((m) => m.id === editingId.value) ?? null)

const apiKeyHint = computed(() => {
  if (editingModel.value?.has_api_key) {
    return t('A key is stored (ends in {hint}). Leave blank to keep it.', { hint: editingModel.value.api_key_hint })
  }
  return t('Leave blank for local models that need no authentication.')
})
const apiKeyPlaceholder = computed(() => (editingModel.value?.has_api_key ? '••••••••••••' : 'sk-...'))

async function loadModels() {
  isLoading.value = true
  try {
    models.value = await listModelConfigs()
  } catch (err: any) {
    showErrorToast(err?.response?.data?.msg || err?.message || t('Failed to load models'))
  } finally {
    isLoading.value = false
  }
}

onMounted(loadModels)

function resetForm() {
  form.id = ''
  form.name = ''
  form.model = ''
  form.base_url = ''
  form.api_key = ''
  form.clear_api_key = false
  form.enabled = true
  form.is_local = false
  form.provider = 'openai'
  form.tool_profile = 'full'
  formError.value = ''
  selectedPresetId.value = 'openai'
}

function applyPreset(preset: ModelProviderPreset) {
  selectedPresetId.value = preset.id
  form.provider = preset.provider
  form.base_url = preset.base_url ?? ''
  form.is_local = preset.is_local
}

function openCreateForm() {
  resetForm()
  editingId.value = null
  formOpen.value = true
}

function openEditForm(m: ModelConfigEntry) {
  editingId.value = m.id
  form.id = m.id
  form.name = m.name
  form.model = m.model
  form.base_url = m.base_url ?? ''
  form.api_key = ''
  form.clear_api_key = false
  form.enabled = m.enabled
  form.is_local = m.is_local
  form.provider = m.provider
  form.tool_profile = m.tool_profile
  formError.value = ''
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
}

async function handleSave() {
  formError.value = ''
  isSaving.value = true
  try {
    if (editingId.value) {
      await updateModelConfig(editingId.value, {
        name: form.name,
        model: form.model,
        base_url: form.base_url || null,
        api_key: form.api_key || undefined,
        clear_api_key: form.clear_api_key,
        enabled: form.enabled,
        is_local: form.is_local,
        provider: form.provider,
        tool_profile: form.tool_profile,
      })
      showSuccessToast(t('Model updated'))
    } else {
      await createModelConfig({
        id: form.id,
        name: form.name,
        model: form.model,
        provider: form.provider,
        base_url: form.base_url || null,
        api_key: form.api_key || null,
        is_local: form.is_local,
        enabled: form.enabled,
        tool_profile: form.tool_profile,
      })
      showSuccessToast(t('Model added'))
    }
    formOpen.value = false
    encryptionWarning.value = false
    await loadModels()
  } catch (err: any) {
    const msg = err?.response?.data?.msg || err?.message || t('Failed to save model')
    formError.value = msg
    if (typeof msg === 'string' && msg.includes('MODEL_ENCRYPTION_KEY')) {
      encryptionWarning.value = true
    }
  } finally {
    isSaving.value = false
  }
}

async function handleDelete(m: ModelConfigEntry) {
  showConfirmDialog({
    title: t('Delete this model?'),
    content: t('It will no longer appear in the model dropdown. Sessions already using it will show an error until switched.'),
    confirmText: t('Delete'),
    cancelText: t('Cancel'),
    confirmType: 'danger',
    onConfirm: async () => {
      try {
        await deleteModelConfig(m.id)
        showSuccessToast(t('Model deleted'))
        await loadModels()
      } catch (err: any) {
        showErrorToast(err?.response?.data?.msg || err?.message || t('Failed to delete model'))
      }
    },
  })
}

async function handleTest(m: ModelConfigEntry) {
  testingId.value = m.id
  delete testResults[m.id]
  try {
    testResults[m.id] = await testModelConnection(m.id)
  } catch (err: any) {
    testResults[m.id] = { ok: false, error: err?.response?.data?.msg || err?.message || t('Test failed') }
  } finally {
    testingId.value = null
  }
}
</script>

<style scoped>
.settings-input {
  @apply h-9 w-full rounded-[10px] bg-[var(--fill-tsp-white-main)] px-3 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-disable)] focus:ring-[1.5px] focus:ring-[var(--border-dark)];
}
</style>
