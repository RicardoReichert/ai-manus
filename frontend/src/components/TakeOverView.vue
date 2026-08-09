<template>
    <div v-if="shouldShow" class="fixed bg-[var(--background-gray-main)] z-50 transition-all w-full h-full inset-0">
        <div class="w-full h-full">
            <VNCViewer
                :session-id="sessionId"
                :enabled="shouldShow"
                :view-only="false"
                v-bind="urlResolver ? { urlResolver } : {}"
            />
        </div>
        <div class="absolute bottom-4 left-1/2 -translate-x-1/2">
            <button @click="exitTakeOver"
                class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] gap-[6px] text-sm rounded-full border-2 border-[var(--border-dark)] shadow-[0px_8px_32px_0px_rgba(0,0,0,0.32)]">
                <span class="text-sm font-medium text-[var(--text-onblack)]">{{ t('Exit Takeover') }}</span>
            </button>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import VNCViewer from './VNCViewer.vue';
import { eventBus } from '../utils/eventBus';

const route = useRoute();
const { t } = useI18n();

// Takeover state
const takeOverActive = ref(false);
const currentSessionId = ref('');
const currentUrlResolver = ref<((sessionId: string) => string) | undefined>(undefined);

const handleTakeOverEvent = (payload: { sessionId: string; active: boolean; urlResolver?: (sessionId: string) => string }) => {
    takeOverActive.value = payload.active;
    currentSessionId.value = payload.sessionId;
    currentUrlResolver.value = payload.urlResolver;
};

// Calculate whether to show takeover view
const shouldShow = computed(() => {
    // Check component state first (from takeover event)
    if (takeOverActive.value && currentSessionId.value) {
        return true;
    }
    
    // Also check route parameters (for direct URL access or page refresh)
    const { params: { sessionId }, query: { vnc } } = route;
    // Only show if both sessionId exists in route AND vnc=1 in query
    return !!sessionId && vnc === '1';
});

onMounted(() => {
    eventBus.on('ui:takeover', handleTakeOverEvent);
});

onBeforeUnmount(() => {
    eventBus.off('ui:takeover', handleTakeOverEvent);
});

// Get session ID
const sessionId = computed(() => {
    return currentSessionId.value || route.params.sessionId as string || '';
});

// Optional resolver for non-Manus-Agent sessions (e.g. Claw); undefined keeps VNCViewer's default
const urlResolver = computed(() => currentUrlResolver.value);

// Exit takeover functionality
const exitTakeOver = () => {
    // Update local state
    takeOverActive.value = false;
    currentSessionId.value = '';
    currentUrlResolver.value = undefined;
};

// Expose sessionId for parent component to use
defineExpose({
    sessionId
});
</script>

