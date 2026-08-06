<template>
  <div class="absolute inset-0 z-[1000] pointer-events-auto">
    <div class="w-full h-full bg-black/60 backdrop-blur-[4px] fixed inset-0" @click="emit('cancel')" />
    <div
      role="dialog"
      class="shadow-menu pointer-events-auto fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[360px] max-w-[95%] flex flex-col rounded-[20px] bg-[var(--background-menu-white)]"
    >
      <h3 class="flex items-center justify-between border-b border-b-[var(--border-main)] pt-5 pe-3 pb-[18px] ps-5 shrink-0">
        <span class="text-[16px] font-medium text-[var(--text-primary)]">{{ t('Adjust photo') }}</span>
        <button
          type="button"
          class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)]"
          @click="emit('cancel')"
        >
          <X class="size-5 text-[var(--icon-tertiary)]" />
        </button>
      </h3>

      <div class="p-5 flex flex-col items-center gap-4">
        <div
          ref="viewportRef"
          class="relative overflow-hidden rounded-full bg-black cursor-grab active:cursor-grabbing"
          :style="{ width: `${VIEWPORT_SIZE}px`, height: `${VIEWPORT_SIZE}px` }"
          @mousedown="startDrag"
        >
          <img
            v-if="imageUrl"
            ref="imageRef"
            :src="imageUrl"
            class="absolute select-none pointer-events-none"
            :style="imageStyle"
            @load="onImageLoad"
            draggable="false"
          >
        </div>

        <div class="w-full flex items-center gap-3">
          <span class="text-[13px] text-[var(--text-tertiary)]">{{ t('Zoom') }}</span>
          <input
            type="range"
            min="1"
            max="3"
            step="0.01"
            v-model.number="zoom"
            class="flex-1"
            @input="onZoomChange"
          >
        </div>

        <div class="w-full flex justify-end gap-2">
          <button
            type="button"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 outline outline-1 -outline-offset-1 hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-primary)] outline-[var(--border-btn-main)] bg-transparent h-[32px]"
            @click="emit('cancel')"
          >
            {{ t('Cancel') }}
          </button>
          <button
            type="button"
            :disabled="!imageLoaded"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 bg-[var(--text-primary)] text-[var(--background-gray-main)] h-[32px] disabled:opacity-50"
            @click="save"
          >
            {{ t('Save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { X } from 'lucide-vue-next';
import { fitCoverScale, clampOffset, computeCropSourceRect } from '@/utils/avatarCrop';

const props = defineProps<{ file: File }>();
const emit = defineEmits<{ saved: [blob: Blob]; cancel: [] }>();

const { t } = useI18n();

const VIEWPORT_SIZE = 280;
const OUTPUT_SIZE = 512;

const imageUrl = ref<string>('');
const imageRef = ref<HTMLImageElement | null>(null);
const viewportRef = ref<HTMLDivElement | null>(null);
const imageLoaded = ref(false);
const naturalWidth = ref(0);
const naturalHeight = ref(0);
const zoom = ref(1);
const offsetX = ref(0);
const offsetY = ref(0);

imageUrl.value = URL.createObjectURL(props.file);
onBeforeUnmount(() => URL.revokeObjectURL(imageUrl.value));

const baseScale = computed(() =>
  naturalWidth.value ? fitCoverScale(naturalWidth.value, naturalHeight.value, VIEWPORT_SIZE) : 1,
);
const displayedWidth = computed(() => naturalWidth.value * baseScale.value * zoom.value);
const displayedHeight = computed(() => naturalHeight.value * baseScale.value * zoom.value);

const imageStyle = computed(() => ({
  width: `${displayedWidth.value}px`,
  height: `${displayedHeight.value}px`,
  // Tailwind's preflight sets `img { max-width: 100%; height: auto }`. Our
  // explicit `height` above already overrides the stylesheet's `height:
  // auto`, but `max-width` is a distinct property our inline `width` does
  // NOT override — it kept silently capping the rendered width at the
  // viewport's 280px while height kept growing with zoom, stretching the
  // image. `maxWidth: 'none'` neutralizes that inherited cap.
  maxWidth: 'none',
  transform: `translate(${offsetX.value}px, ${offsetY.value}px)`,
}));

const onImageLoad = () => {
  const img = imageRef.value;
  if (!img) return;
  naturalWidth.value = img.naturalWidth;
  naturalHeight.value = img.naturalHeight;
  // Center the image in the viewport at zoom=1.
  offsetX.value = (VIEWPORT_SIZE - naturalWidth.value * baseScale.value) / 2;
  offsetY.value = (VIEWPORT_SIZE - naturalHeight.value * baseScale.value) / 2;
  imageLoaded.value = true;
};

const clampCurrentOffset = () => {
  const clamped = clampOffset({
    offsetX: offsetX.value,
    offsetY: offsetY.value,
    displayedWidth: displayedWidth.value,
    displayedHeight: displayedHeight.value,
    viewportSize: VIEWPORT_SIZE,
  });
  offsetX.value = clamped.x;
  offsetY.value = clamped.y;
};

const onZoomChange = () => clampCurrentOffset();

let dragging = false;
let dragStartX = 0;
let dragStartY = 0;
let dragOriginX = 0;
let dragOriginY = 0;

const startDrag = (e: MouseEvent) => {
  dragging = true;
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  dragOriginX = offsetX.value;
  dragOriginY = offsetY.value;
  window.addEventListener('mousemove', onDrag);
  window.addEventListener('mouseup', stopDrag);
};

const onDrag = (e: MouseEvent) => {
  if (!dragging) return;
  offsetX.value = dragOriginX + (e.clientX - dragStartX);
  offsetY.value = dragOriginY + (e.clientY - dragStartY);
  clampCurrentOffset();
};

const stopDrag = () => {
  dragging = false;
  window.removeEventListener('mousemove', onDrag);
  window.removeEventListener('mouseup', stopDrag);
};

onBeforeUnmount(stopDrag);

const save = () => {
  const img = imageRef.value;
  if (!img || !imageLoaded.value) return;
  const rect = computeCropSourceRect({
    imageWidth: naturalWidth.value,
    imageHeight: naturalHeight.value,
    viewportSize: VIEWPORT_SIZE,
    offsetX: offsetX.value,
    offsetY: offsetY.value,
    zoom: zoom.value,
  });
  const canvas = document.createElement('canvas');
  canvas.width = OUTPUT_SIZE;
  canvas.height = OUTPUT_SIZE;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.drawImage(img, rect.sx, rect.sy, rect.sSize, rect.sSize, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE);
  canvas.toBlob((blob) => {
    if (blob) emit('saved', blob);
  }, 'image/jpeg', 0.9);
};
</script>
