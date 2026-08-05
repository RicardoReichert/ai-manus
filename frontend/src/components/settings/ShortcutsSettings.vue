<template>
  <div class="space-y-6 w-full">
    <p class="text-[13px] text-[var(--text-tertiary)] leading-[18px]">
      {{ t('Click a shortcut to record a new key combination for it.') }}
    </p>
    <div class="space-y-1">
      <div
        v-for="def in defs"
        :key="def.id"
        class="flex items-center justify-between gap-4 py-3 border-b border-[var(--border-light)] last:border-transparent"
      >
        <span class="text-sm text-[var(--text-primary)]">{{ t(def.label) }}</span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            data-testid="shortcut-recorder"
            class="flex items-center gap-1 rounded-[8px] border px-2 py-1 min-h-[30px] transition-colors"
            :class="recordingId === def.id
              ? 'border-[var(--border-primary)] text-[var(--text-blue)]'
              : 'border-[var(--border-dark)] hover:bg-[var(--fill-tsp-white-light)]'"
            @click="startRecording(def.id)"
          >
            <span v-if="recordingId === def.id" class="text-[12px] px-1">
              {{ t('Press a key combination...') }}
            </span>
            <template v-else>
              <kbd
                v-for="(key, idx) in formatBinding(bindings[def.id])"
                :key="`${def.id}-${idx}`"
                class="inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5 rounded-[6px] bg-[var(--fill-tsp-white-main)] text-[12px] font-medium text-[var(--text-secondary)]"
              >
                {{ key }}
              </kbd>
            </template>
          </button>
          <button
            v-if="!isDefault(def.id)"
            type="button"
            class="text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] underline underline-offset-2"
            @click="resetBinding(def.id)"
          >
            {{ t('Reset') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useShortcuts } from '@/composables/useShortcuts'
import { showErrorToast } from '@/utils/toast'

const { t } = useI18n()
const { defs, bindings, setBinding, resetBinding, isDefault, formatBinding } = useShortcuts()

const recordingId = ref<string | null>(null)
const MODIFIER_ONLY_KEYS = ['Control', 'Meta', 'Shift', 'Alt']

const startRecording = (id: string) => {
  recordingId.value = recordingId.value === id ? null : id
}

const handleRecordKeydown = (event: KeyboardEvent) => {
  if (!recordingId.value) return
  event.preventDefault()
  event.stopPropagation()

  if (event.key === 'Escape') {
    recordingId.value = null
    return
  }
  // Wait for a real key — a bare modifier isn't a usable combination yet.
  if (MODIFIER_ONLY_KEYS.includes(event.key)) return

  if (!event.ctrlKey && !event.metaKey && !event.altKey) {
    showErrorToast(t('Shortcuts need at least one modifier key (Ctrl/Cmd/Alt)'))
    return
  }

  setBinding(recordingId.value, {
    ctrl: event.ctrlKey,
    meta: event.metaKey,
    shift: event.shiftKey,
    alt: event.altKey,
    key: event.key.toLowerCase(),
  })
  recordingId.value = null
}

// Capture in the capture phase so this wins over any other page-level
// shortcut listener (e.g. SessionSidebar's own Ctrl+K handler) while
// recording is active.
window.addEventListener('keydown', handleRecordKeydown, true)
onUnmounted(() => window.removeEventListener('keydown', handleRecordKeydown, true))
</script>
