<template>
  <div class="flex items-center pointer-events-auto relative" ref="triggerRef">
    <button
      type="button"
      class="flex h-8 pt-[7px] md:pr-[6px] pr-[4px] pb-[7px] md:pl-[8px] pl-[6px] justify-center items-center gap-1.5 rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-light)] transition-colors cursor-pointer"
      :aria-expanded="showMenu"
      aria-haspopup="menu"
      @click="toggleMenu"
    >
      <span class="text-[var(--text-primary)] md:text-[16px] text-[15px] font-[500] truncate max-w-[240px]">
        {{ activeModelName || t('Loading...') }}
      </span>
      <span
        v-if="isLocalModel"
        class="text-[10px] leading-none font-semibold text-blue-500 bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.5 rounded shrink-0"
      >
        {{ t('Local') }}
      </span>
      <ChevronDown class="size-3.5 text-[var(--icon-tertiary)] shrink-0" :size="14" />
    </button>

    <!--
      Teleported to <body>: this dropdown can be triggered from inside a
      SimpleBar-scrolled region (e.g. Manus Claw's header, sticky inside a
      scroll container). SimpleBar's content wrapper sets
      `overflow: hidden scroll`, which clips ANY descendant positioned
      absolutely beyond its own box — including position:absolute content
      that's visually "just below" the trigger, sticky or not. The menu was
      present in the DOM and even clickable via direct coordinates, but
      invisible: exactly the "opens but shows nothing" bug reported.
      Teleporting escapes that clipping ancestor entirely, matching the
      pattern the Settings dialog already uses (reka-ui's DialogPortal).
      Position is computed from the trigger's real screen coordinates since
      the menu is no longer a positioned descendant of it once teleported.
    -->
    <Teleport to="body">
      <div
        v-if="showMenu"
        ref="menuContentRef"
        role="menu"
        class="fixed z-50 min-w-[260px] max-w-[340px] max-h-[420px] overflow-y-auto rounded-[12px] border border-[var(--border-light)] bg-[var(--background-menu-white)] shadow-[0px_8px_32px_0px_var(--shadow-S)] p-1.5 space-y-1"
        :style="menuPositionStyle"
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
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
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

const activeModel = computed<ModelDescriptor | undefined>(() => {
  if (!isControlled) return undefined
  // modelId === null means "use the registry default" (e.g. Claw with no
  // explicit choice yet) — there is no model whose id is null, so falling
  // through to availableModels[0] (same convention as the shared/uncontrolled
  // path) resolves it to a real name instead of leaving the label stuck on
  // "Loading..." forever once the list has actually loaded.
  if (props.modelId === null) return availableModels.value[0]
  return availableModels.value.find((m) => m.id === props.modelId)
})
// Resolved id, not the raw prop: a controlled null must highlight/check the
// actual default entry in the menu below, not match nothing.
const selectedModelId = computed(() =>
  isControlled ? (activeModel.value?.id ?? null) : sharedSelectedModelId.value,
)
const activeModelName = computed(() => (isControlled ? activeModel.value?.name : sharedActiveModelName.value))
const isLocalModel = computed(() => (isControlled ? (activeModel.value?.is_local ?? false) : sharedIsLocalModel.value))

const showMenu = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const menuContentRef = ref<HTMLElement | null>(null)
const menuPosition = reactive({ top: 0, left: 0 })

// max-w-[340px] in the template; kept in sync here to flip the menu
// leftward near the right edge instead of overflowing off-screen.
const MENU_MAX_WIDTH = 340
const MENU_GAP = 6

function updateMenuPosition() {
  const trigger = triggerRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  let left = rect.left
  if (left + MENU_MAX_WIDTH > window.innerWidth) {
    left = Math.max(8, rect.right - MENU_MAX_WIDTH)
  }
  menuPosition.top = rect.bottom + MENU_GAP
  menuPosition.left = left
}

const menuPositionStyle = computed(() => ({
  top: `${menuPosition.top}px`,
  left: `${menuPosition.left}px`,
}))

async function toggleMenu() {
  if (showMenu.value) {
    showMenu.value = false
    return
  }
  updateMenuPosition()
  showMenu.value = true
  // The menu teleports to <body> and only exists in the DOM once showMenu
  // flips true; wait a tick before relying on its real (post-render) size
  // for the edge-flip check above, which already used the trigger's own
  // rect and needs no further correction — kept for clarity/future use if
  // the menu's own width ever needs measuring instead of assuming max-width.
  await nextTick()
}

const selectModel = (model: ModelDescriptor) => {
  showMenu.value = false
  emit('update:modelId', model.id)
}

const selectTaskMode = (mode: 'agent' | 'chat') => {
  showMenu.value = false
  emit('update:taskMode', mode)
}

const handleOutsideClick = (e: MouseEvent) => {
  const target = e.target as Node
  // The menu is teleported to <body>, so it's no longer a DOM descendant of
  // triggerRef — checking only triggerRef would make every click inside the
  // menu register as "outside" and close it before the item's own @click
  // (selectModel/selectTaskMode) ever runs.
  const insideTrigger = triggerRef.value?.contains(target)
  const insideMenu = menuContentRef.value?.contains(target)
  if (!insideTrigger && !insideMenu) {
    showMenu.value = false
  }
}

const handleReposition = () => {
  if (showMenu.value) updateMenuPosition()
}

onMounted(() => {
  document.addEventListener('mousedown', handleOutsideClick)
  // The trigger can sit inside a scrolled ancestor (SimpleBar) that never
  // fires window 'scroll' — capture:true catches scroll events from any
  // scrollable ancestor, not just the window.
  window.addEventListener('scroll', handleReposition, true)
  window.addEventListener('resize', handleReposition)
  ensureModelsLoaded()
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleOutsideClick)
  window.removeEventListener('scroll', handleReposition, true)
  window.removeEventListener('resize', handleReposition)
})
</script>
