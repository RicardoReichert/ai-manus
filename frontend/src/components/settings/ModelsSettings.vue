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

        <FormField v-if="!editingId" :label="t('Registry ID')" :hint="t('Used internally; cannot be changed after creation. Letters, numbers, \'.\', \'_\', \'-\' only — it becomes part of a URL, so it cannot contain \'/\'.')">
          <input v-model="form.id" class="settings-input" placeholder="my-gpt-4o" @input="sanitizeId" />
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

        <FormField :label="t('Description')" :hint="t('Shown under the model name in the dropdown. Leave empty to show nothing.')">
          <input v-model="form.description" class="settings-input" :placeholder="t('Optional')" />
        </FormField>

        <FormField :label="t('Tool profile')">
          <div class="flex gap-1.5">
            <button
              v-for="profile in (['full', 'lean'] as const)"
              :key="profile"
              type="button"
              :title="profile === 'full' ? t('Full profile tooltip') : t('Lean profile tooltip')"
              class="h-8 px-3 rounded-[8px] text-[13px] font-medium clickable border"
              :class="form.tool_profile === profile
                ? 'border-[var(--Button-black)] text-[var(--text-primary)]'
                : 'border-[var(--Button-border-secondary)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-light)]'"
              @click="onProfileChange(profile)"
            >
              {{ profile === 'full' ? t('Full') : t('Lean') }}
            </button>
          </div>
          <p class="text-[11px] text-[var(--text-tertiary)]">
            {{ form.tool_profile === 'full' ? t('Full profile tooltip') : t('Lean profile tooltip') }}
          </p>
        </FormField>

        <FormField :label="t('Tools')" :hint="t('By default the profile above decides. Customize to pick exactly which tools this model can call.')">
          <label class="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer mb-2">
            <input v-model="customizeTools" type="checkbox" class="rounded" @change="onCustomizeToolsToggle" />
            {{ t('Customize tool list') }}
          </label>
          <div v-if="customizeTools" class="space-y-3 rounded-[10px] bg-[var(--fill-tsp-white-main)] p-3">
            <div v-for="group in toolGroupsForCurrentProfile" :key="group.toolkit">
              <p class="text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider mb-1">{{ group.toolkit }}</p>
              <label
                v-for="tool in group.tools"
                :key="tool.name"
                class="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer py-0.5"
                :title="tool.description"
              >
                <input
                  type="checkbox"
                  class="rounded"
                  :checked="checkedTools.has(tool.name)"
                  @change="toggleTool(tool.name)"
                />
                {{ tool.name }}
              </label>
            </div>
            <p v-if="toolGroupsForCurrentProfile.length === 0" class="text-[12px] text-[var(--text-tertiary)]">
              {{ t('Loading...') }}
            </p>
          </div>
        </FormField>

        <FormField v-if="editingModel" :label="t('Detected capabilities')" :hint="t('Auto-detected from the model name; only informational here.')">
          <div class="flex flex-wrap gap-1.5 text-[12px] text-[var(--text-secondary)]">
            <span class="px-2 py-1 rounded bg-[var(--fill-tsp-white-main)]">
              {{ editingModel.capabilities.max_tools ? t('Tool budget: {n}', { n: editingModel.capabilities.max_tools }) : t('No tool limit') }}
            </span>
            <span v-if="editingModel.capabilities.needs_guided_decoding" class="px-2 py-1 rounded bg-[var(--fill-tsp-white-main)]">
              {{ t('Guided decoding') }}
            </span>
            <span v-if="editingModel.capabilities.context_window" class="px-2 py-1 rounded bg-[var(--fill-tsp-white-main)]">
              {{ t('{n} token context', { n: editingModel.capabilities.context_window.toLocaleString() }) }}
            </span>
            <span class="px-2 py-1 rounded bg-[var(--fill-tsp-white-main)]">
              {{ editingModel.capabilities_auto_detected ? t('Auto-detected') : t('Manually set') }}
            </span>
          </div>
        </FormField>

        <label class="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer">
          <input v-model="form.is_local" type="checkbox" class="rounded" />
          {{ t('Local model (runs on your network, e.g. LM Studio, Ollama)') }}
        </label>

        <label class="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer">
          <input v-model="form.enabled" type="checkbox" class="rounded" />
          {{ t('Enabled (visible in the model dropdown)') }}
        </label>

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
  listAvailableTools, MODEL_PROVIDER_PRESETS, type ModelConfigEntry, type ModelProviderPreset,
  type ToolProfile, type TestConnectionResult, type ToolInfo,
} from '@/api/modelConfig'
import { useDialog } from '@/composables/useDialog'
import { useActiveModel } from '@/composables/useActiveModel'
import { showSuccessToast, showErrorToast } from '@/utils/toast'

const { t } = useI18n()
const { refreshModels } = useActiveModel()
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
  enabled: true,
  is_local: false,
  provider: 'openai',
  tool_profile: 'full' as ToolProfile,
  description: '',
})

// Per-model tool picker (Perfil de ferramentas). Loaded once; independent of
// which model is being created/edited.
const availableTools = ref<ToolInfo[]>([])
const toolProfileDefaults = ref<Record<ToolProfile, string[]>>({ full: [], lean: [] })
const customizeTools = ref(false)
const checkedTools = reactive(new Set<string>())

async function loadAvailableTools() {
  try {
    const { tools, profiles } = await listAvailableTools()
    availableTools.value = tools
    toolProfileDefaults.value = profiles
  } catch (err: any) {
    console.warn('Failed to load available tools:', err?.message)
  }
}

// Toolkits a given profile actually grants (mirrors the backend's
// domain/services/tools/profiles.py): full gets the raw browser toolkit,
// lean gets the single delegation tool instead — never both.
const TOOLKITS_BY_PROFILE: Record<ToolProfile, string[]> = {
  full: ['shell', 'browser', 'file', 'message', 'search'],
  lean: ['shell', 'delegation', 'file', 'message', 'search'],
}

const toolGroupsForCurrentProfile = computed(() => {
  const allowedToolkits = TOOLKITS_BY_PROFILE[form.tool_profile]
  const byToolkit = new Map<string, ToolInfo[]>()
  for (const tool of availableTools.value) {
    if (!allowedToolkits.includes(tool.toolkit)) continue
    if (!byToolkit.has(tool.toolkit)) byToolkit.set(tool.toolkit, [])
    byToolkit.get(tool.toolkit)!.push(tool)
  }
  return allowedToolkits
    .filter((tk) => byToolkit.has(tk))
    .map((toolkit) => ({ toolkit, tools: byToolkit.get(toolkit)! }))
})

function toggleTool(name: string) {
  if (checkedTools.has(name)) {
    checkedTools.delete(name)
  } else {
    checkedTools.add(name)
  }
}

function seedCheckedToolsFromProfile() {
  checkedTools.clear()
  for (const name of toolProfileDefaults.value[form.tool_profile] || []) {
    checkedTools.add(name)
  }
}

function onCustomizeToolsToggle() {
  // Turning it on with nothing picked yet starts from "everything the
  // profile already grants" rather than an empty (= nothing callable) list.
  if (customizeTools.value && checkedTools.size === 0) {
    seedCheckedToolsFromProfile()
  }
}

function onProfileChange(profile: ToolProfile) {
  form.tool_profile = profile
  // A custom selection from the other profile could reference toolkits this
  // one doesn't grant (e.g. browser_* tools while switching into lean) —
  // reseed from the new profile's own defaults instead of carrying it over.
  if (customizeTools.value) {
    seedCheckedToolsFromProfile()
  }
}

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

onMounted(() => {
  loadModels()
  loadAvailableTools()
})

function resetForm() {
  form.id = ''
  form.name = ''
  form.model = ''
  form.base_url = ''
  form.api_key = ''
  form.enabled = true
  form.is_local = false
  form.provider = 'openai'
  form.tool_profile = 'full'
  form.description = ''
  formError.value = ''
  selectedPresetId.value = 'openai'
  customizeTools.value = false
  checkedTools.clear()
}

// Mirrors the backend's _ID_PATTERN (interfaces/schemas/model_config.py):
// the id is embedded as a single URL path segment on every route but create
// (GET/PATCH/DELETE/test all key off it). A '/' — natural to type, since
// that's how provider model names look ("google/gemma-4-e4b") — makes every
// follow-up action 404 even though creation itself succeeds, because FastAPI
// reads it as two path segments. Stripped live so it can't be typed at all,
// rather than only caught after a failed save.
function sanitizeId(event: Event) {
  const input = event.target as HTMLInputElement
  const sanitized = input.value.replace(/[^A-Za-z0-9._-]/g, '')
  if (sanitized !== input.value) {
    input.value = sanitized
  }
  form.id = sanitized
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
  form.enabled = m.enabled
  form.is_local = m.is_local
  form.provider = m.provider
  form.tool_profile = m.tool_profile
  form.description = m.description ?? ''
  formError.value = ''
  customizeTools.value = m.enabled_tools.length > 0
  checkedTools.clear()
  for (const name of m.enabled_tools) checkedTools.add(name)
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
}

async function handleSave() {
  formError.value = ''
  isSaving.value = true
  // Empty list means "use the profile's default set" (backend contract, see
  // domain/services/tools/profiles.py) — only send an explicit list when the
  // admin actually opted into customizing it.
  const enabled_tools = customizeTools.value ? Array.from(checkedTools) : []
  try {
    if (editingId.value) {
      await updateModelConfig(editingId.value, {
        name: form.name,
        model: form.model,
        base_url: form.base_url || null,
        api_key: form.api_key || undefined,
        enabled: form.enabled,
        is_local: form.is_local,
        provider: form.provider,
        tool_profile: form.tool_profile,
        description: form.description || null,
        enabled_tools,
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
        description: form.description || null,
        enabled_tools,
      })
      showSuccessToast(t('Model added'))
    }
    formOpen.value = false
    encryptionWarning.value = false
    await loadModels()
    // Every other part of the app (chat dropdown, Manus Claw dropdown) reads
    // from useActiveModel's cached list — without this, an admin's change
    // here is invisible everywhere else until a full page reload.
    await refreshModels()
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
        await refreshModels()
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
