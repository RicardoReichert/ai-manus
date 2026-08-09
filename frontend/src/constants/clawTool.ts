/**
 * Claw tool-call kind resolution — OpenClaw tool names are free-form (no
 * fixed list ships in this repo), so kind is resolved by pattern-matching
 * the name rather than an exhaustive map, with a generic fallback for
 * anything unrecognized. Drives which section ClawToolDetailView.vue
 * renders and which icon ClawToolLogView.vue shows per row.
 */
import ShellIcon from '@/components/icons/ShellIcon.vue';
import EditIcon from '@/components/icons/EditIcon.vue';
import BrowserIcon from '@/components/icons/BrowserIcon.vue';
import SearchIcon from '@/components/icons/SearchIcon.vue';
import { Wrench } from 'lucide-vue-next';

export type ClawToolKind = 'shell' | 'file' | 'browser' | 'search' | 'generic';

const KIND_PATTERNS: [RegExp, ClawToolKind][] = [
  [/^(bash|shell|exec|run.?command|terminal)/i, 'shell'],
  [/^(file|read|write|edit|create|apply.?patch|str.?replace|cat|view)/i, 'file'],
  [/^browser/i, 'browser'],
  [/^(grep|glob|search|find)/i, 'search'],
];

export function resolveClawToolKind(name: string): ClawToolKind {
  for (const [pattern, kind] of KIND_PATTERNS) {
    if (pattern.test(name)) return kind;
  }
  return 'generic';
}

export const CLAW_TOOL_ICON_MAP: Record<ClawToolKind, unknown> = {
  shell: ShellIcon,
  file: EditIcon,
  browser: BrowserIcon,
  search: SearchIcon,
  generic: Wrench,
};

/** First string-valued arg matching any of the given keys — used to pull
 * out a tool's "headline" argument (a command, a file path, a URL, a
 * query) without needing a name-keyed map of which field means what. */
export function firstArg(args: Record<string, unknown> | undefined, keys: string[]): string | undefined {
  if (!args) return undefined;
  for (const key of keys) {
    const v = args[key];
    if (typeof v === 'string' && v) return v;
  }
  return undefined;
}

/** Strips the sandbox's home-directory prefix from a file path, matching
 * composables/useTool.ts's equivalent stripping for the Manus Agent side. */
export function stripHomePrefix(path: string): string {
  return path.replace(/^\/home\/(ubuntu|node)\//, '');
}
