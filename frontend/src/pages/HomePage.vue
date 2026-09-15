<template>
  <SimpleBar>
    <div
      class="flex flex-col h-full flex-1 min-w-0 mx-auto w-full sm:min-w-[390px] px-5 justify-center items-start gap-2 relative max-w-full sm:max-w-full">
      <!-- Header -->
      <div class="w-[calc(100%+40px)] -mx-5 bg-[var(--background-gray-main)] sticky top-0 z-10 ps-[14px] pe-[20px] py-[12px] border-b border-transparent">
        <div class="flex justify-between items-center w-full">
          <div class="relative z-20 items-center flex-shrink-0 flex">
            <ModelSelectorDropdown
              :taskMode="taskMode"
              @update:modelId="setSelectedModel"
              @update:taskMode="taskMode = $event" />
          </div>
          <div class="flex items-center gap-2">
            <a v-if="showGithubButton"
               :href="githubRepositoryUrl"
               target="_blank"
               rel="noopener noreferrer"
               class="clickable hidden sm:flex h-8 items-center justify-center gap-1 rounded-[8px] border border-[var(--border-main)] ps-2 pe-3 text-[14px] font-medium leading-[20px] tracking-[-0.15px] text-[var(--text-primary)] hover:bg-[var(--fill-tsp-white-main)]"
               title="Visit GitHub Repository">
              <Github :size="16" />
              GitHub
            </a>
          </div>
        </div>
      </div>

      <div class="w-full max-w-full sm:max-w-[680px] sm:min-w-[390px] mx-auto mt-auto mb-auto pb-[8vh]">
        <div class="w-full flex flex-col items-center justify-center pb-8 gap-1">
          <span v-if="greetingName" class="text-[var(--text-tertiary)] text-center font-serif text-[22px] leading-[30px]"
            :style="{ fontFamily: serifFontFamily }">
            {{ $t('Hello') }}, {{ greetingName }}
          </span>
          <h1 class="text-[var(--text-primary)] text-center font-serif text-[36px] leading-[46px] sm:text-[40px] sm:leading-[52px]"
            :style="{ fontFamily: serifFontFamily }">
            {{ $t('What can I do for you?') }}
          </h1>
        </div>
        <div class="flex flex-col gap-1 w-full">
          <ChatBox
            ref="chatBoxRef"
            v-model="message"
            v-model:attachments="attachments"
            :rows="2"
            :isRunning="isSubmitting"
            :hideStopButton="true"
            @submit="handleSubmit"
          />
        </div>
        <div class="flex flex-wrap items-center gap-1.5 pt-2 justify-center">
          <button
            v-for="chip in visibleChips"
            :key="chip.label"
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors clickable cursor-pointer"
            :class="chip.action === 'chat-mode' && taskMode === 'chat'
              ? 'bg-[var(--fill-blue)] text-[var(--text-blue)] hover:bg-[var(--fill-blue)]'
              : 'bg-[var(--fill-tsp-white-main)] hover:bg-[var(--fill-tsp-white-dark)] text-[var(--text-secondary)]'"
            @click="handleChipClick(chip)"
          >
            <component :is="chip.icon" :size="14" :class="chip.action === 'chat-mode' && taskMode === 'chat' ? 'text-[var(--icon-blue)]' : 'text-[var(--icon-tertiary)]'" />
            <span>{{ $t(chip.label) }}</span>
          </button>

          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-[var(--fill-tsp-white-main)] hover:bg-[var(--fill-tsp-white-dark)] text-[var(--text-secondary)] transition-colors clickable cursor-pointer"
            @click="showAllChips = !showAllChips"
          >
            <span>{{ showAllChips ? $t('Collapse') || 'Less' : $t('More') }}</span>
          </button>
        </div>
      </div>

    </div>
  </SimpleBar>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, type FunctionalComponent } from 'vue';
import SimpleBar from '../components/SimpleBar.vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import ModelSelectorDropdown from '../components/ModelSelectorDropdown.vue';
import { createSession } from '../api/agent';
import { showErrorToast } from '../utils/toast';
import {
  Github, Presentation, Globe, Palette, Gamepad2, Table,
  AppWindow, Video, CalendarClock, Telescope, BarChart3, Music,
  MessagesSquare, BookOpen,
} from 'lucide-vue-next';
import type { FileInfo } from '../api/file';
import { useFilePreviewer } from '../composables/useFilePreviewer';
import { useAuth } from '../composables/useAuth';
import { consumePendingHomeDraft, pendingHomeDraft } from '../composables/usePendingHomeMessage';
import { getCachedClientConfig } from '../api/config';
import { useActiveModel } from '../composables/useActiveModel';

const { t } = useI18n();
const router = useRouter();
const message = ref('');
const isSubmitting = ref(false);
const attachments = ref<FileInfo[]>([]);
const chatBoxRef = ref<InstanceType<typeof ChatBox> | null>(null);
const { hideFilePreviewer } = useFilePreviewer();
const { currentUser } = useAuth();
const showGithubButton = ref(false);
const githubRepositoryUrl = ref('https://github.com/simpleyyt/ai-manus');
const { selectedModelId, ensureModelsLoaded, refreshModels, setSelectedModel } = useActiveModel();
const taskMode = ref<'agent' | 'chat'>('agent');

const serifFontFamily = 'ui-serif, Georgia, Cambria, "Times New Roman", Times, serif';

const greetingName = computed(() => currentUser.value?.fullname || '');

interface SuggestionChip {
  label: string;
  prompt: string;
  icon: FunctionalComponent;
  /** 'chat-mode' switches the composer to chat mode instead of filling a prompt. */
  action?: 'chat-mode';
}

const primaryChips: SuggestionChip[] = [
  { label: 'Create slides', prompt: 'Create slides prompt', icon: Presentation },
  { label: 'Build website', prompt: 'Build website prompt', icon: Globe },
  { label: 'Design', prompt: 'Design prompt', icon: Palette },
  { label: 'Create games', prompt: 'Create games prompt', icon: Gamepad2 },
];

// Official Manus "More" list. "Scheduled task" falls back to a plain prompt
// fill for now — it should open the scheduling modal (TAREFA 15.2), which
// isn't built yet; wire it up once that modal exists.
const extraChips: SuggestionChip[] = [
  { label: 'Develop apps', prompt: 'Develop apps prompt', icon: AppWindow },
  { label: 'Video', prompt: 'Video prompt', icon: Video },
  { label: 'Scheduled task', prompt: 'Scheduled task prompt', icon: CalendarClock },
  { label: 'Wide Research', prompt: 'Wide Research prompt', icon: Telescope },
  { label: 'Create spreadsheet', prompt: 'Create spreadsheet prompt', icon: Table },
  { label: 'Visualization', prompt: 'Visualization prompt', icon: BarChart3 },
  { label: 'Audio', prompt: 'Audio prompt', icon: Music },
  { label: 'Chat mode', prompt: '', icon: MessagesSquare, action: 'chat-mode' },
  { label: 'Playbook', prompt: 'Playbook prompt', icon: BookOpen },
];

const showAllChips = ref(false);
const visibleChips = computed(() =>
  showAllChips.value ? [...primaryChips, ...extraChips] : primaryChips
);

const handleChipClick = (chip: SuggestionChip) => {
  if (chip.action === 'chat-mode') {
    taskMode.value = taskMode.value === 'chat' ? 'agent' : 'chat';
    return;
  }
  message.value = t(chip.prompt);
  chatBoxRef.value?.focus();
};

const applyPendingHomeDraft = async () => {
  const draft = consumePendingHomeDraft();
  if (!draft) return;
  await nextTick();
  chatBoxRef.value?.seedDraft(draft);
};

watch(pendingHomeDraft, (draft) => {
  if (draft) void applyPendingHomeDraft();
});

onMounted(async () => {
  hideFilePreviewer();
  ensureModelsLoaded();
  await applyPendingHomeDraft();
  const clientConfig = await getCachedClientConfig();
  if (clientConfig) {
    showGithubButton.value = clientConfig.show_github_button;
    githubRepositoryUrl.value = clientConfig.github_repository_url;
  }
});

const handleSubmit = async (requiredSkills: { id: string; name: string }[] = []) => {
  if (message.value.trim() && !isSubmitting.value) {
    isSubmitting.value = true;

    try {
      // Reconcile against the live registry first: a model deleted or
      // disabled by an admin since this id was cached would otherwise 400
      // ("Unknown model") here — silently, from the user's side, since they
      // never touched the dropdown. refreshModels() falls back to the
      // current default when the cached id no longer resolves.
      await refreshModels();
      const session = await createSession(undefined, taskMode.value, selectedModelId.value || undefined);
      const sessionId = session.session_id;

      router.push({
        path: `/chat/${sessionId}`,
        state: {
          message: message.value,
          taskMode: taskMode.value,
          requiredSkills,
          files: attachments.value.map((file: FileInfo) => ({
            file_id: file.file_id,
            filename: file.filename,
            content_type: file.content_type,
            size: file.size,
            upload_date: file.upload_date
          }))
        }
      });
    } catch (error) {
      console.error('Failed to create session:', error);
      showErrorToast(t('Failed to create session, please try again later'));
      isSubmitting.value = false;
    }
  }
};
</script>
