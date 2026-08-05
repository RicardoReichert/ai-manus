<template>
  <div class="flex items-center pointer-events-auto relative" ref="menuRef">
    <button
      type="button"
      class="flex h-8 pt-[7px] md:pr-[6px] pr-[4px] pb-[7px] md:pl-[8px] pl-[6px] justify-center items-center gap-1.5 rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-light)] transition-colors cursor-pointer"
      :aria-expanded="showMenu"
      aria-haspopup="menu"
      @click="showMenu = !showMenu"
    >
      <span class="text-[var(--text-primary)] md:text-[16px] text-[15px] font-[500] truncate max-w-[240px]">
        {{ activeModelName || t('Loading...') }}
      </span>
      <span
        v-if="isLocalModel"
        class="text-[10px] font-semibold text-blue-500 bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.5 rounded shrink-0"
      >
        {{ t('Local') }}
      </span>
      <ChevronDown class="size-3.5 text-[var(--icon-tertiary)] shrink-0" :size="14" />
    </button>

    <div
      v-if="showMenu"
      role="menu"
      class="absolute top-[calc(100%+6px)] left-0 z-50 min-w-[260px] max-w-[340px] max-h-[420px] overflow-y-auto rounded-[12px] border border-[var(--border-light)] bg-[var(--background-menu-white)] shadow-[0px_8px_32px_0px_var(--shadow-S)] p-1.5 space-y-1"
    >
      <div class="px-2 py-1 text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
        {{ t('Available Models') }}
      </div>
      <button
        v-for="m in availableModels"
        :key="m.id"
        type="button"
        role="menuitemradio"
        :aria-checked="selectedModelId === m.id"
        class="flex w-full flex-col text-start gap-0.5 px-2.5 py-2 rounded-[8px] hover:bg-[var(--fill-tsp-white-main)] transition-colors cursor-pointer"
        :class="selectedModelId === m.id ? 'bg-[var(--fill-tsp-white-main)]' : ''"
        @click="selectModel(m)"
      >
        <div class="flex items-center justify-between w-full">
          <span class="text-sm font-medium text-[var(--text-primary)] truncate">{{ m.name }}</span>
          <span v-if="m.is_local" class="text-[10px] font-semibold text-blue-500 bg-blue-500/10 px-1 rounded ml-1">{{ t('Local') }}</span>
          <Check v-if="selectedModelId === m.id" :size="16" class="text-[var(--icon-primary)] shrink-0 ml-1" />
        </div>
        <span v-if="m.description" class="text-[11px] text-[var(--text-tertiary)] line-clamp-1">
          {{ m.description }}
        </span>
      </button>

      <template v-if="props.sessionId">
        <div class="border-t border-[var(--border-light)] my-1"></div>
        <div class="px-2 py-1 text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
          {{ t('Task Mode') }}
        </div>
        <button
          v-for="mode in (['agent', 'chat'] as const)"
          :key="mode"
          type="button"
          role="menuitemradio"
          :aria-checked="props.taskMode === mode"
          class="flex w-full items-center justify-between px-2.5 py-2 rounded-[8px] hover:bg-[var(--fill-tsp-white-main)] transition-colors cursor-pointer"
          :class="props.taskMode === mode ? 'bg-[var(--fill-tsp-white-main)]' : ''"
          @click="selectTaskMode(mode)"
        >
          <span class="text-sm font-medium text-[var(--text-primary)]">{{ mode === 'agent' ? t('Agent') : t('Chat') }}</span>
          <Check v-if="props.taskMode === mode" :size="16" class="text-[var(--icon-primary)] shrink-0" />
        </button>

        <div class="border-t border-[var(--border-light)] my-1"></div>
        <div class="px-2.5 py-1.5 text-[11px] text-[var(--text-tertiary)]">
          {{ t('Applies to your next message') }}
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, Check } from 'lucide-vue-next'
import type { ModelDescriptor } from '../api/model'
import { useActiveModel } from '../composables/useActiveModel'

const props = defineProps<{
  sessionId?: string
  taskMode?: 'agent' | 'chat'
  /**
   * Controlled selection, e.g. Claw's per-instance model. When set, the
   * dropdown displays/selects this id instead of the shared chat selection
   * (useActiveModel's singleton) — the two pickers must not overwrite each
   * other's state.
   */
  modelId?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelId', id: string): void
  (e: 'update:taskMode', mode: 'agent' | 'chat'): void
}>()

const { t } = useI18n()
const isControlled = props.modelId !== undefined
const {
  availableModels,
  selectedModelId: sharedSelectedModelId,
  activeModelName: sharedActiveModelName,
  isLocalModel: sharedIsLocalModel,
  ensureModelsLoaded,
} = useActiveModel()

const selectedModelId = computed(() => (isControlled ? props.modelId : sharedSelectedModelId.value))
const activeModel = computed<ModelDescriptor | undefined>(() =>
  isControlled ? availableModels.value.find((m) => m.id === props.modelId) : undefined,
)
const activeModelName = computed(() => (isControlled ? activeModel.value?.name : sharedActiveModelName.value))
const isLocalModel = computed(() => (isControlled ? (activeModel.value?.is_local ?? false) : sharedIsLocalModel.value))

const showMenu = ref(false)
const menuRef = ref<HTMLElement | null>(null)

const selectModel = (model: ModelDescriptor) => {
  showMenu.value = false
  emit('update:modelId', model.id)
}

const selectTaskMode = (mode: 'agent' | 'chat') => {
  showMenu.value = false
  emit('update:taskMode', mode)
}

const handleOutsideClick = (e: MouseEvent) => {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    showMenu.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleOutsideClick)
  ensureModelsLoaded()
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleOutsideClick)
})
</script>
