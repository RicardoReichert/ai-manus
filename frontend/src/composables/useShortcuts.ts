import { ref } from 'vue'

/**
 * Device-local, editable keyboard shortcuts (TAREFA 17.2).
 *
 * Same client-only persistence model as useChromePrefs.ts — a shortcut is a
 * per-device preference, not something to sync across sessions. MVP scope
 * covers the one shortcut the app actually wires up today (New Task); adding
 * a new entry to SHORTCUT_DEFS plus a real keydown handler picking it up
 * (see SessionSidebar.vue's handleKeydown) is how a future action becomes
 * user-editable.
 */

export interface ShortcutBinding {
  ctrl: boolean
  meta: boolean
  shift: boolean
  alt: boolean
  /** event.key, lowercased (e.g. 'k', '/', 'enter') */
  key: string
}

export interface ShortcutDef {
  id: string
  label: string
  default: ShortcutBinding
}

const STORAGE_PREFIX = 'manus-shortcut-'

const isMac = typeof navigator !== 'undefined'
  && /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent)

export const SHORTCUT_DEFS: ShortcutDef[] = [
  {
    id: 'new-task',
    label: 'New task',
    default: { ctrl: !isMac, meta: isMac, shift: false, alt: false, key: 'k' },
  },
]

function isValidBinding(value: unknown): value is ShortcutBinding {
  return (
    typeof value === 'object' && value !== null
    && typeof (value as ShortcutBinding).key === 'string'
    && typeof (value as ShortcutBinding).ctrl === 'boolean'
    && typeof (value as ShortcutBinding).meta === 'boolean'
    && typeof (value as ShortcutBinding).shift === 'boolean'
    && typeof (value as ShortcutBinding).alt === 'boolean'
  )
}

function readBinding(id: string, fallback: ShortcutBinding): ShortcutBinding {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + id)
    if (!raw) return fallback
    const parsed = JSON.parse(raw)
    return isValidBinding(parsed) ? parsed : fallback
  } catch {
    return fallback
  }
}

function writeBinding(id: string, binding: ShortcutBinding): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + id, JSON.stringify(binding))
  } catch {
    /* ignore — e.g. private browsing quota */
  }
}

const bindings = ref<Record<string, ShortcutBinding>>(
  Object.fromEntries(SHORTCUT_DEFS.map((def) => [def.id, readBinding(def.id, def.default)])),
)

export function useShortcuts() {
  const setBinding = (id: string, binding: ShortcutBinding) => {
    bindings.value = { ...bindings.value, [id]: binding }
    writeBinding(id, binding)
  }

  const resetBinding = (id: string) => {
    const def = SHORTCUT_DEFS.find((d) => d.id === id)
    if (def) setBinding(id, def.default)
  }

  const isDefault = (id: string): boolean => {
    const def = SHORTCUT_DEFS.find((d) => d.id === id)
    const current = bindings.value[id]
    if (!def || !current) return true
    return (
      current.ctrl === def.default.ctrl
      && current.meta === def.default.meta
      && current.shift === def.default.shift
      && current.alt === def.default.alt
      && current.key === def.default.key
    )
  }

  const matches = (id: string, event: KeyboardEvent): boolean => {
    const b = bindings.value[id]
    if (!b) return false
    return (
      !!event.ctrlKey === b.ctrl
      && !!event.metaKey === b.meta
      && !!event.shiftKey === b.shift
      && !!event.altKey === b.alt
      && event.key.toLowerCase() === b.key.toLowerCase()
    )
  }

  const formatBinding = (b: ShortcutBinding): string[] => {
    const parts: string[] = []
    if (b.ctrl) parts.push('Ctrl')
    if (b.meta) parts.push(isMac ? '⌘' : 'Win')
    if (b.alt) parts.push(isMac ? '⌥' : 'Alt')
    if (b.shift) parts.push(isMac ? '⇧' : 'Shift')
    parts.push(b.key.length === 1 ? b.key.toUpperCase() : b.key)
    return parts
  }

  return { defs: SHORTCUT_DEFS, bindings, setBinding, resetBinding, isDefault, matches, formatBinding }
}
