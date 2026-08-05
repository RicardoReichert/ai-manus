<template>
  <div class="flex size-full min-h-0 min-w-0 flex-1 flex-col bg-[var(--background-gray-main)]">
    <div class="flex h-[56px] w-full shrink-0 items-center justify-between py-[12px] ps-[14px] pe-[20px] md:px-[24px] gap-[8px]">
      <div class="flex-1 text-lg font-[500] leading-[28px] text-[var(--text-primary)]">
        {{ t('Agent') }}
      </div>
      <div class="flex items-center gap-1">
        <button
          v-if="sessionId"
          type="button"
          class="flex items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)] size-8 text-[var(--icon-secondary)]"
          :title="t('Open task')"
          @click="openSession"
        >
          <ExternalLink :size="18" />
        </button>
        <button
          type="button"
          class="flex items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)] size-8 text-[var(--icon-secondary)]"
          :title="t('Library')"
          @click="router.push('/library')"
        >
          <Bookmark :size="18" />
        </button>
      </div>
    </div>

    <div class="w-full flex-1 min-h-0 overflow-y-auto">
      <div class="max-w-[680px] mx-auto w-full px-5 md:px-6 pb-10 pt-4">
        <div v-if="loading" class="py-16 text-center text-sm text-[var(--text-tertiary)]">
          {{ t('Loading...') }}
        </div>

        <div v-else-if="!sessionId" class="py-16 text-center text-sm text-[var(--text-tertiary)]">
          {{ t('Create a task to get started') }}
        </div>

        <template v-else>
          <div v-if="planTitle" class="text-[var(--text-primary)] text-base font-medium mb-1">
            {{ planTitle }}
          </div>
          <div v-if="goal" class="text-[var(--text-tertiary)] text-sm mb-4">
            {{ goal }}
          </div>

          <!-- Subtasks panel -->
          <div class="rounded-[12px] border border-[var(--border-main)] overflow-hidden">
            <div class="flex items-center justify-between px-4 py-3 border-b border-[var(--border-main)]">
              <span class="text-sm font-medium text-[var(--text-primary)]">{{ t('Subtasks') }}</span>
              <span class="text-xs text-[var(--text-tertiary)]">{{ steps.length }}</span>
            </div>
            <div v-if="steps.length === 0" class="px-4 py-8 text-center text-sm text-[var(--text-tertiary)]">
              {{ t('No plan yet') }}
            </div>
            <div v-else class="flex flex-col">
              <div
                v-for="step in steps"
                :key="step.id"
                class="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border-light)] last:border-transparent"
              >
                <PlanStepIcon :status="(step.status as StepEventData['status'])" />
                <span class="flex-1 min-w-0 truncate text-sm text-[var(--text-primary)]">{{ step.description }}</span>
                <span v-if="formatDuration(step.duration_ms)" class="shrink-0 text-xs text-[var(--text-tertiary)] tabular-nums">
                  {{ formatDuration(step.duration_ms) }}
                </span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Bookmark, ExternalLink } from 'lucide-vue-next'
import PlanStepIcon from '../components/PlanStepIcon.vue'
import { getSessions, getSessionSubtasks, type SubtaskItem } from '../api/agent'
import { formatDuration } from '../utils/duration'
import type { StepEventData } from '../types/event'

const { t } = useI18n()
const router = useRouter()

const loading = ref(true)
const sessionId = ref<string | null>(null)
const planTitle = ref<string | null>(null)
const goal = ref<string | null>(null)
const steps = ref<SubtaskItem[]>([])

const load = async () => {
  loading.value = true
  try {
    // "Agente" isn't tied to a specific task in the URL — it shows the
    // Subtasks panel for whatever task the user was most recently on.
    const res = await getSessions()
    const latest = res.sessions[0]
    if (!latest) {
      sessionId.value = null
      return
    }
    sessionId.value = latest.session_id
    const subtasks = await getSessionSubtasks(latest.session_id)
    planTitle.value = subtasks.plan_title
    goal.value = subtasks.goal
    steps.value = subtasks.steps
  } catch (e) {
    console.error('Failed to load agent subtasks', e)
    sessionId.value = null
  } finally {
    loading.value = false
  }
}

const openSession = () => {
  if (sessionId.value) router.push(`/chat/${sessionId.value}`)
}

onMounted(load)
</script>
