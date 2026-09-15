<template>
  <!-- Plain object: key/value rows, nested composites indented under their key. -->
  <div v-if="isPlainObject(value)" class="flex flex-col gap-[6px]">
    <div v-for="(v, k) in value as Record<string, unknown>" :key="k" class="flex flex-col gap-[2px]">
      <span class="text-[11px] font-[500] text-[var(--text-tertiary)]">{{ k }}</span>
      <ClawValueView
        v-if="isComposite(v) && depth < maxDepth"
        :value="v"
        :depth="depth + 1"
        :maxDepth="maxDepth"
        class="ps-[10px] border-s-2 border-[var(--border-main)]" />
      <span v-else :class="['text-[12px]', 'whitespace-pre-wrap', 'break-words', primitiveClass(v)]">{{ formatLeaf(v) }}</span>
    </div>
  </div>

  <!-- Array: numbered rows, same composite/leaf split per item. -->
  <div v-else-if="Array.isArray(value)" class="flex flex-col gap-[6px]">
    <div v-for="(v, i) in value" :key="i" class="flex items-start gap-[6px]">
      <span class="shrink-0 text-[11px] font-mono text-[var(--text-tertiary)]">#{{ i + 1 }}</span>
      <ClawValueView
        v-if="isComposite(v) && depth < maxDepth"
        :value="v"
        :depth="depth + 1"
        :maxDepth="maxDepth"
        class="min-w-0 flex-1" />
      <span v-else :class="['min-w-0 flex-1', 'text-[12px]', 'whitespace-pre-wrap', 'break-words', primitiveClass(v)]">{{ formatLeaf(v) }}</span>
    </div>
  </div>

  <!-- Leaf value at the top level (e.g. a plain string/number result) — no key to label it with. -->
  <span v-else :class="['text-[12px]', 'whitespace-pre-wrap', 'break-words', primitiveClass(value)]">{{ formatLeaf(value) }}</span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  value: unknown;
  /** Recursion guard: composites past this depth fall back to a compact
   * inline JSON string instead of nesting further disclosure levels. */
  depth?: number;
  maxDepth?: number;
}>(), {
  depth: 0,
  maxDepth: 4,
});

const isComposite = (v: unknown): v is Record<string, unknown> | unknown[] =>
  v !== null && typeof v === 'object';

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  isComposite(v) && !Array.isArray(v);

const primitiveClass = (v: unknown): string => {
  if (v === null || v === undefined) return 'text-[var(--text-tertiary)] italic';
  if (typeof v === 'boolean' || typeof v === 'number') return 'font-mono text-[var(--text-blue)]';
  if (isComposite(v)) return 'font-mono text-[var(--text-secondary)]'; // depth cutoff fallback
  return 'text-[var(--text-primary)]';
};

const formatLeaf = (v: unknown): string => {
  if (v === null) return 'null';
  if (v === undefined) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'boolean' || typeof v === 'number') return String(v);
  // Composite past maxDepth — compact fallback, not pretty-printed.
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
};
</script>
