<template>
  <div dir="ltr" class="relative flex flex-col flex-1 min-h-0 h-full w-full">
    <div
      ref="terminalEl"
      class="agent-workspace-terminal-panel flex-1 min-h-0 outline-none overflow-hidden w-full h-full"
      :class="isDark ? 'agent-workspace-terminal-panel-dark' : 'agent-workspace-terminal-panel-light'"
    />
    <div
      v-if="exited"
      class="absolute inset-0 flex items-center justify-center bg-[var(--background-gray-main)]/80 text-[13px] text-[var(--text-tertiary)]">
      {{ t('Terminal session ended') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { ClawTerminalClient, ClawTerminalMessage } from '@/api/claw';

const props = defineProps<{
  sessionId: string;
}>();

const { t } = useI18n();

const terminalEl = ref<HTMLElement | null>(null);
const isDark = ref(false);
const exited = ref(false);

let term: Terminal | null = null;
let fitAddon: FitAddon | null = null;
let resizeObserver: ResizeObserver | null = null;
let themeObserver: MutationObserver | null = null;
let client: ClawTerminalClient | null = null;

const cssVar = (styles: CSSStyleDeclaration, name: string, fallback = '') =>
  styles.getPropertyValue(name).trim() || fallback;

/**
 * Same theme construction as ShellToolView.vue, but the cursor stays visible
 * here (interactive terminal), so it isn't matched to the background.
 */
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
    if (term && client?.isConnected) {
      client.resize(term.cols, term.rows);
    }
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
    cursorBlink: true,
    cursorStyle: 'block',
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
  term.focus();

  term.onData((data) => {
    client?.sendInput(data);
  });

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

const onTerminalMessage = (message: ClawTerminalMessage) => {
  if (message.type === 'data' && message.data) {
    term?.write(message.data);
  } else if (message.type === 'exit') {
    exited.value = true;
  } else if (message.type === 'error') {
    exited.value = true;
  }
};

const connect = () => {
  const cols = term?.cols;
  const rows = term?.rows;
  client = new ClawTerminalClient(
    props.sessionId,
    {
      onMessage: onTerminalMessage,
      onClose: () => {
        exited.value = true;
      },
    },
    cols,
    rows,
  );
};

onMounted(() => {
  initTerminal();
  connect();
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
  client?.disconnect();
  client = null;
  term?.dispose();
  term = null;
  fitAddon = null;
});
</script>
