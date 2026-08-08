<template>
  <div dir="ltr" class="relative flex flex-col flex-1 min-h-0 h-full w-full">
    <div
      ref="terminalEl"
      class="agent-workspace-terminal-panel flex-1 min-h-0 outline-none overflow-hidden w-full h-full"
      :class="isDark ? 'agent-workspace-terminal-panel-dark' : 'agent-workspace-terminal-panel-light'"
    />
    <div
      v-if="!hasActivity"
      class="absolute inset-0 flex items-center justify-center bg-[var(--background-gray-main)]/80 text-[13px] text-[var(--text-tertiary)]">
      {{ t('No agent activity yet') }}
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Read-only, live echo of the agent's own tool calls, formatted as terminal
 * output — NOT a real PTY (OpenClaw's internal tool-execution shell isn't
 * exposed anywhere the frontend can attach to). Each 'tool' ClawEvent the
 * page already receives is written here as `$ <name> <args>` on `start`,
 * streamed text on `update`, and the final result (in red if `isError`) on
 * `result` — reusing the exact same xterm.js setup/theme as
 * ClawTerminalView.vue, just with stdin disabled.
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { summarizeToolArgs, type ClawEvent } from '@/api/claw';

const props = defineProps<{
  event?: ClawEvent | null;
}>();

const { t } = useI18n();

const terminalEl = ref<HTMLElement | null>(null);
const isDark = ref(false);
const hasActivity = ref(false);

let term: Terminal | null = null;
let fitAddon: FitAddon | null = null;
let resizeObserver: ResizeObserver | null = null;
let themeObserver: MutationObserver | null = null;
// Tracks whether the last frame written for a given toolCallId ended mid-line
// (e.g. a streamed 'update' with no trailing newline), so the next frame for
// a *different* call still starts on its own line.
let lastCallId: string | undefined;
let lastEndedWithNewline = true;

const cssVar = (styles: CSSStyleDeclaration, name: string, fallback = '') =>
  styles.getPropertyValue(name).trim() || fallback;

// Same theme construction as ClawTerminalView.vue (kept in sync manually —
// this component is read-only so the cursor is hidden instead of blinking).
const xtermTheme = (dark: boolean) => {
  const styles = getComputedStyle(document.documentElement);
  const bg = cssVar(styles, '--background-gray-main', dark ? '#272728' : '#f8f8f7');
  const selection = cssVar(styles, '--background-selection', dark ? '#264f78' : '#b8d3f8');
  const thumb = cssVar(styles, '--terminal-panel-scrollbar-thumb', 'transparent');
  const thumbHover = cssVar(styles, '--terminal-panel-scrollbar-thumb-hover', thumb);
  const base = {
    background: bg,
    selectionBackground: selection,
    selectionInactiveBackground: selection,
    scrollbarSliderBackground: thumb,
    scrollbarSliderHoverBackground: thumbHover,
    scrollbarSliderActiveBackground: thumbHover,
  };
  if (dark) return base;

  const primary = cssVar(styles, '--text-primary', '#34322d');
  const secondary = cssVar(styles, '--text-secondary', '#858481');
  const tertiary = cssVar(styles, '--text-tertiary', '#b0aea5');
  const themePrimary = cssVar(styles, '--theme-text-primary', '#262626');
  const blue = cssVar(styles, '--text-blue', cssVar(styles, '--text-brand', '#0081f2'));
  const blueDark = cssVar(styles, '--text-blue-dark', blue);
  const error = cssVar(styles, '--function-error', '#f44336');
  const success = cssVar(styles, '--function-success', '#25ba3b');
  const warning = cssVar(styles, '--function-warning', '#ef9c2c');
  return {
    ...base,
    foreground: primary,
    black: primary,
    blue,
    brightBlack: tertiary,
    brightBlue: blue,
    brightCyan: blue,
    brightGreen: success,
    brightMagenta: blueDark,
    brightRed: error,
    brightWhite: themePrimary,
    brightYellow: warning,
    cyan: blue,
    green: success,
    magenta: blueDark,
    red: error,
    white: secondary,
    yellow: warning,
  };
};

const detectDark = () =>
  document.documentElement.classList.contains('dark')
  || document.body.classList.contains('dark');

const fit = () => {
  try {
    fitAddon?.fit();
  } catch {
    // ignore fit errors during teardown
  }
};

const initTerminal = () => {
  if (!terminalEl.value || term) return;
  isDark.value = detectDark();
  const options: ConstructorParameters<typeof Terminal>[0] = {
    allowProposedApi: true,
    convertEol: true,
    cursorInactiveStyle: 'none',
    disableStdin: true,
    customGlyphs: true,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
    fontSize: 14,
    lineHeight: 1.15,
    scrollback: 10000,
    theme: xtermTheme(isDark.value),
  };
  try {
    if (document.createElement('canvas').getContext('2d')) {
      options.overviewRuler = { width: 8 };
    }
  } catch {
    // jsdom: no canvas
  }
  term = new Terminal(options);
  fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(terminalEl.value);
  fit();

  let skipFirst = true;
  resizeObserver = new ResizeObserver(() => {
    if (skipFirst) {
      skipFirst = false;
      return;
    }
    fit();
  });
  resizeObserver.observe(terminalEl.value);
};

/** ANSI color helpers — xterm.js writes raw ANSI escapes, same as a real shell would. */
const ANSI_RESET = '\x1b[0m';
const ANSI_CYAN = '\x1b[36m';
const ANSI_RED = '\x1b[31m';

const stringifyResult = (value: unknown): string => {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const ensureOwnLine = (callId: string | undefined) => {
  if (lastCallId !== undefined && lastCallId !== callId && !lastEndedWithNewline) {
    term?.write('\r\n');
    lastEndedWithNewline = true;
  }
  lastCallId = callId;
};

const writeChunk = (text: string) => {
  if (!text || !term) return;
  term.write(text);
  lastEndedWithNewline = text.endsWith('\n') || text.endsWith('\r\n');
};

const writeEvent = (event: ClawEvent) => {
  if (!term) return;
  hasActivity.value = true;
  ensureOwnLine(event.toolCallId);

  if (event.phase === 'start') {
    writeChunk(`${ANSI_CYAN}$ ${event.name || 'tool'} ${summarizeToolArgs(event.args)}${ANSI_RESET}\r\n`);
    return;
  }

  if (event.phase === 'update' && event.partialResult !== undefined) {
    writeChunk(stringifyResult(event.partialResult));
    return;
  }

  if (event.phase === 'result') {
    const text = stringifyResult(event.result);
    if (text) {
      writeChunk(event.isError ? `${ANSI_RED}${text}${ANSI_RESET}` : text);
    }
    if (!lastEndedWithNewline) writeChunk('\r\n');
  }
};

watch(() => props.event, (event) => {
  if (event) writeEvent(event);
});

onMounted(() => {
  initTerminal();
  if (props.event) writeEvent(props.event);
  themeObserver = new MutationObserver(() => {
    const dark = detectDark();
    if (dark !== isDark.value && term) {
      isDark.value = dark;
      term.options.theme = xtermTheme(dark);
    }
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
});

onBeforeUnmount(() => {
  themeObserver?.disconnect();
  themeObserver = null;
  resizeObserver?.disconnect();
  resizeObserver = null;
  term?.dispose();
  term = null;
  fitAddon = null;
});
</script>
