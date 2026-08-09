<template>
  <Popover v-model:open="isOpen">
    <PopoverTrigger>
      <button type="button"
        class="flex items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)] size-8 text-[var(--icon-secondary)]"
        :title="t('Usage')">
        <Gauge class="size-[18px]" :size="18" />
      </button>
    </PopoverTrigger>
    <PopoverContent align="end">
      <div class="w-[280px] flex flex-col bg-[var(--background-menu-white)] rounded-2xl shadow-[0px_8px_32px_0px_var(--shadow-S),0px_0px_0px_1px_var(--border-light)]">
        <div class="flex py-3 px-4 justify-between items-center border-b border-[var(--border-main)]">
          <h3 class="text-[var(--text-primary)] text-base font-medium leading-[22px]">{{ t('Usage') }}</h3>
        </div>

        <div v-if="loading" class="py-8 text-center text-sm text-[var(--text-tertiary)]">
          {{ t('Loading...') }}
        </div>
        <div v-else-if="usage" class="p-4 flex flex-col gap-3">
          <div class="flex items-center justify-between text-sm">
            <span class="text-[var(--text-tertiary)]">{{ t('Time worked') }}</span>
            <span class="text-[var(--text-primary)] font-medium tabular-nums">{{ formattedWorkedTime }}</span>
          </div>
          <div class="flex items-center justify-between text-sm">
            <span class="text-[var(--text-tertiary)]">{{ t('Pages viewed') }}</span>
            <span class="text-[var(--text-primary)] font-medium tabular-nums">{{ usage.pages_viewed }}</span>
          </div>
          <div class="flex items-center justify-between text-sm">
            <span class="text-[var(--text-tertiary)]">{{ t('Commands run') }}</span>
            <span class="text-[var(--text-primary)] font-medium tabular-nums">{{ usage.commands_run }}</span>
          </div>
          <div class="flex items-center justify-between text-sm">
            <span class="text-[var(--text-tertiary)]">{{ t('APIs called') }}</span>
            <span class="text-[var(--text-primary)] font-medium tabular-nums">{{ usage.api_calls }}</span>
          </div>
          <div class="flex items-center justify-between text-sm">
            <span class="text-[var(--text-tertiary)]">{{ t('Files created') }}</span>
            <span class="text-[var(--text-primary)] font-medium tabular-nums">{{ usage.files_created }}</span>
          </div>

          <div class="w-full h-[1px] bg-[var(--border-main)] my-1" />

          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--text-tertiary)]">{{ t('Rate this task') }}</span>
            <div class="flex items-center gap-0.5">
              <button
                v-for="n in 5"
                :key="n"
                type="button"
                data-testid="usage-star"
                class="clickable cursor-pointer p-0.5"
                :title="String(n)"
                @click="handleRate(n)"
              >
                <Star
                  :size="16"
                  :class="(usage.rating ?? 0) >= n ? 'text-[var(--function-warning)]' : 'text-[var(--icon-tertiary)]'"
                  :fill="(usage.rating ?? 0) >= n ? 'var(--function-warning)' : 'none'"
                />
              </button>
            </div>
          </div>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Gauge, Star } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { getSessionUsage, rateSession, type SessionUsage } from '../api/agent'
import { formatDuration } from '../utils/duration'
import { showErrorToast } from '../utils/toast'

const props = defineProps<{ sessionId?: string }>()

const { t } = useI18n()
const isOpen = ref(false)
const loading = ref(false)
const usage = ref<SessionUsage | null>(null)

const formattedWorkedTime = computed(() => formatDuration(usage.value?.worked_ms) || '0:00')

const load = async () => {
  const sid = props.sessionId
  if (!sid) return
  loading.value = true
  try {
    usage.value = await getSessionUsage(sid)
  } catch (e) {
    console.error('Failed to load session usage', e)
    usage.value = null
  } finally {
    loading.value = false
  }
}

watch(isOpen, (open) => {
  if (open) load()
})

const handleRate = async (rating: number) => {
  const sid = props.sessionId
  if (!usage.value || !sid) return
  const nextRating = usage.value.rating === rating ? null : rating
  const previous = usage.value.rating
  usage.value = { ...usage.value, rating: nextRating }
  try {
    await rateSession(sid, nextRating)
  } catch {
    usage.value = { ...usage.value, rating: previous }
    showErrorToast(t('Failed to update rating'))
  }
}
</script>
