# Frontend Test Suite (Pure Logic + Composables + Critical API + Router) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the frontend (`frontend/src/`) to solid test coverage across its highest-value layers — pure-logic utils, composables, the three critical API infrastructure modules (`client.ts`, `chatWs.ts`, `config.ts`), and the router auth guard — plus close two infra gaps (coverage tooling, CI).

**Architecture:** All new tests are plain Vitest `*.spec.ts` files, colocated in a sibling `__tests__/` directory next to the file under test, following the exact conventions already established by the 21 existing spec files in this repo (see Global Constraints). No new test framework, no new mocking library, no Pinia (there is none in this app — state is module-scope singleton `ref()`s exported from composables).

**Tech Stack:** Vitest 4.1.9, `@vue/test-utils` 2.4.11, jsdom 29, TypeScript. New devDependency: `@vitest/coverage-v8`.

## Global Constraints

- **File location/naming:** every new test goes in a sibling `__tests__/` directory, named `<SourceFileName>.spec.ts`. `vitest.config.ts`'s `include` is `src/**/*.spec.ts` — a `.test.ts` file silently never runs.
- **`globals: false`** — every spec file must explicitly `import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'` (only import what you use).
- **No Pinia, no Vuex** — this app has no store layer. Global state = module-scope `ref()`s exported by composables. This means: **state persists across `it()` blocks within the same test file** (and across files that share a Vitest worker, though Vitest isolates modules per file by default via `pool: 'threads'`/module re-evaluation — confirm by checking that a fresh `import` at the top of each spec file gives a clean module instance; if a test needs a *guaranteed* fresh module-level state — e.g. localStorage-seeded initial value, or a module-level cache flag — use `vi.resetModules()` followed by a dynamic `const mod = await import('../thePath')` inside that specific `it()`, not a static top-level import).
- **i18n:** the real singleton instance lives at `frontend/src/composables/useI18n.ts`, exported as `i18n` (default export too) — configured with `legacy: false` (Composition API mode). This means **`useI18n()` imported from the `'vue-i18n'` package requires an active component `setup()` context to work** — it throws/returns broken state if called outside one. Composables that call `useI18n()` internally (`useDialog`, `useTime`'s `useCustomTime`, `useToolInfo` in `useTool.ts`) or functions that call it (`formatRelativeTime` in `utils/time.ts`) **cannot be tested by calling them bare** — mount a minimal host component:
  ```ts
  import { defineComponent } from 'vue'
  import { mount } from '@vue/test-utils'
  import { i18n } from '../useI18n'

  function withSetup<T>(setup: () => T) {
    let result!: T
    const wrapper = mount(
      defineComponent({ setup() { result = setup(); return () => null } }),
      { global: { plugins: [i18n] } }
    )
    return { result, wrapper }
  }
  ```
  Use this `withSetup` pattern (place it locally in each spec that needs it — no shared test-utils module exists yet, matching current repo convention of inlining helpers per spec file) for any composable using `useI18n()` or lifecycle hooks (`onMounted`/`onUnmounted`).
- **API mocking:** `vi.mock('../../api/<module>', () => ({ fnName: vi.fn() }))`, then `vi.mocked(fnName).mockResolvedValue(...)`/`mockRejectedValue(...)`. Exception: `api/client.spec.ts` tests `client.ts` itself (the infra), so it does NOT mock `axios`/`./client` — see Task 22.
- **No coverage threshold enforced this round** — `@vitest/coverage-v8` is added for visibility only (Task 1); do not add a `thresholds` block to `vitest.config.ts`.
- Run `cd frontend && npm run test` after every task; the full existing suite (21 specs) must stay green throughout — a new spec must never touch/modify an existing one.

---

### Task 1: Coverage tooling

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vitest.config.ts`

**Interfaces:**
- Produces: `npm run test:coverage` script; `coverage` block in Vitest config. No other task depends on this beyond the fact it must not break `npm run test`.

- [ ] **Step 1:** `cd frontend && npm i -D @vitest/coverage-v8`
- [ ] **Step 2:** In `frontend/vitest.config.ts`, add a `coverage` block inside the existing `test: {...}` object:
  ```ts
  coverage: {
    provider: 'v8',
    reporter: ['text', 'html'],
    include: ['src/**/*.ts', 'src/**/*.vue'],
    exclude: ['src/**/__tests__/**', 'src/**/*.spec.ts'],
  },
  ```
- [ ] **Step 3:** In `frontend/package.json` `scripts`, add: `"test:coverage": "vitest run --coverage"` (keep existing `test`/`test:watch` untouched).
- [ ] **Step 4:** Run `cd frontend && npm run test:coverage` — verify it completes and prints a coverage table (existing 21 specs only, at this point).
- [ ] **Step 5:** Commit: `git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts && git commit -m "test(frontend): add coverage tooling (@vitest/coverage-v8)"`

---

### Task 2: CI workflow for frontend tests

**Files:**
- Create: `.github/workflows/frontend-tests.yml`

**Interfaces:**
- Produces: a CI job independent of every other task — safe to do any time, no dependency on the new spec files existing yet.

- [ ] **Step 1:** Create `.github/workflows/frontend-tests.yml`:
  ```yaml
  name: Frontend Tests

  on:
    push:
      branches: ['**']
      paths:
        - 'frontend/**'
        - '.github/workflows/frontend-tests.yml'
    pull_request:
      paths:
        - 'frontend/**'
        - '.github/workflows/frontend-tests.yml'

  jobs:
    test:
      runs-on: ubuntu-latest
      defaults:
        run:
          working-directory: frontend
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-node@v4
          with:
            node-version: '20'
            cache: 'npm'
            cache-dependency-path: frontend/package-lock.json
        - run: npm ci
        - run: npm run type-check
        - run: npm run lint
        - run: npm test
  ```
- [ ] **Step 2:** Validate YAML syntax locally: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/frontend-tests.yml'))"` (or any available YAML linter) — must not error.
- [ ] **Step 3:** Commit: `git add .github/workflows/frontend-tests.yml && git commit -m "ci(frontend): run type-check/lint/test on push and PR"`

---

### Task 3: `utils/dom.spec.ts`

**Files:**
- Create: `frontend/src/utils/__tests__/dom.spec.ts`
- Source: `frontend/src/utils/dom.ts` (exports `getParentElement(selector: string | HTMLElement | Element, parentSelector?: string): HTMLElement | null` and `async copyToClipboard(text: string): Promise<boolean>`)

- [ ] Cover `getParentElement`:
  - Given a CSS selector string matching an element in `document.body.innerHTML`, returns its `parentElement`.
  - Given an `HTMLElement` reference directly (not a selector string), same behavior.
  - Given a `parentSelector`, returns `element.closest(parentSelector)` instead of the immediate parent.
  - Returns `null` (and does not throw) when the selector matches nothing, or when `parentSelector` finds no ancestor.
- [ ] Cover `copyToClipboard`:
  - When `navigator.clipboard.writeText` is available and resolves: stub it with `vi.fn().mockResolvedValue(undefined)` via `Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true })`; assert it returns `true` and `writeText` was called with the given text.
  - When `navigator.clipboard.writeText` rejects: assert it falls through to the `document.execCommand('copy')` fallback path (mock `document.execCommand = vi.fn().mockReturnValue(true)`) and still returns `true`.
  - When `navigator.clipboard` is entirely absent (`Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })`): assert it goes straight to the fallback textarea path.
  - When the fallback `document.execCommand` also returns `false`/throws: assert the function returns `false` and does not throw.
- [ ] Run `cd frontend && npm test -- dom.spec` — passing.
- [ ] Commit: `git add frontend/src/utils/__tests__/dom.spec.ts && git commit -m "test(frontend): cover utils/dom.ts"`

---

### Task 4: `utils/eventBus.spec.ts`

**Files:**
- Create: `frontend/src/utils/__tests__/eventBus.spec.ts`
- Source: `frontend/src/utils/eventBus.ts` (exports `eventBus` — a typed `mitt<AppEvents>()` instance — plus string constants `UI_SHOW_FILE_PREVIEWER`, `UI_SHOW_COMPUTER_PANEL`, `UI_OPEN_PLAN_PANEL`)

- [ ] A handler registered with `eventBus.on('ui:toast', handler)` receives the exact payload passed to `eventBus.emit('ui:toast', payload)`.
- [ ] `eventBus.off('ui:toast', handler)` stops the handler from being called on a subsequent `emit`.
- [ ] An event with `undefined` payload type (e.g. `'projects:changed'`) can be emitted/received with no payload argument.
- [ ] Two independently-registered handlers for the same event both fire.
- [ ] Run `cd frontend && npm test -- eventBus.spec` — passing.
- [ ] Commit: `git add frontend/src/utils/__tests__/eventBus.spec.ts && git commit -m "test(frontend): cover utils/eventBus.ts"`

---

### Task 5: `utils/time.spec.ts`

**Files:**
- Create: `frontend/src/utils/__tests__/time.spec.ts`
- Source: `frontend/src/utils/time.ts` (exports `parseISODateTime(isoString: string): number`, `formatRelativeTime(timestamp: number): string`, `formatCustomTime(timestamp: number, t?: (key: string) => string, locale?: string): string`)

- [ ] `parseISODateTime`:
  - Given `"2025-06-22T04:42:11.842000"`-style ISO string, returns `Math.floor(date.getTime() / 1000)` — assert against a manually computed `new Date(iso).getTime() / 1000 | 0`.
  - Given an unparseable string, throws `Error` containing `"Failed to parse ISO datetime string"`.
- [ ] `formatRelativeTime` — **needs the `withSetup` host-component pattern from Global Constraints** (it calls `useI18n()` from `'vue-i18n'` internally). Use `vi.useFakeTimers().setSystemTime(...)` to control "now":
  - `now - 30s` → `"Just now"` (real i18n key, real translated text — do not mock i18n, per convention).
  - `now - 5min` → contains `"5"` and the translated `"minutes ago"`.
  - `now - 3h` → hours-ago branch.
  - `now - 10d` → days-ago branch.
  - `now - 6mo` → months-ago branch.
  - `now - 2yr` → years-ago branch.
- [ ] `formatCustomTime` (pure — no i18n needed when `t` is omitted, uses the fallback English weekday array):
  - A timestamp for "today" (use `vi.useFakeTimers()` + construct a same-day `Date`) → `HH:MM` 24h format (`hour12:false`); assert `locale` starting with `'zh'` vs not doesn't change the *format* for today (both use time, per source: the zh/en branch is dead code today — assert current actual behavior, not aspirational behavior).
  - A timestamp within the current Mon–Sun week but not today → returns the English weekday name (e.g. `'Tuesday'`) when no `t` is passed; when a `t` stub `(k) => `T:${k}`` is passed, returns `'T:Tuesday'` (asserts it calls `t(weekdays[date.getDay()])`).
  - A timestamp this year but not this week → `MM/DD` for both `locale='en'` and `locale='zh'` (source produces the same format for both branches today — assert actual behavior).
  - A timestamp from a previous year → `YYYY/MM`.
- [ ] Run `cd frontend && npm test -- time.spec` — passing.
- [ ] Commit: `git add frontend/src/utils/__tests__/time.spec.ts && git commit -m "test(frontend): cover utils/time.ts"`

---

### Task 6: `utils/toast.spec.ts`

**Files:**
- Create: `frontend/src/utils/__tests__/toast.spec.ts`
- Source: `frontend/src/utils/toast.ts` (exports `showToast(options: {message,type?,duration?} | string)`, `showErrorToast(message, duration?)`, `showInfoToast(message, duration?)`, `showSuccessToast(message, duration?)`; also mounts `window.toast = {show,error,info,success}` as an import-time side effect)
- Reference: `frontend/src/utils/eventBus.ts` for the `'ui:toast'` event shape

- [ ] `showToast('hello')` (string form) emits `'ui:toast'` on `eventBus` with `{ message: 'hello', type: 'info', duration: 3000 }` (register a listener via `eventBus.on('ui:toast', spy)` before calling, assert `spy` was called with that exact object).
- [ ] `showToast({ message: 'x', type: 'error', duration: 500 })` (object form) emits with those exact fields passed through.
- [ ] `showToast({ message: 'x' })` with no `type`/`duration` defaults to `type: 'info', duration: 3000`.
- [ ] `showToast({ message: 'x', duration: 0 })` — `duration: 0` is preserved as `0`, not overridden by the `3000` default (source uses `config.duration === undefined ? 3000 : config.duration`, so `0` must survive).
- [ ] `showErrorToast('x')` emits `type: 'error'`; `showInfoToast('x')` emits `type: 'info'`; `showSuccessToast('x')` emits `type: 'success'`.
- [ ] `window.toast.show === showToast`, `window.toast.error === showErrorToast`, etc. (import-time global mount).
- [ ] Run `cd frontend && npm test -- toast.spec` — passing.
- [ ] Commit: `git add frontend/src/utils/__tests__/toast.spec.ts && git commit -m "test(frontend): cover utils/toast.ts"`

---

### Task 7: `lib/utils.spec.ts`

**Files:**
- Create: `frontend/src/lib/__tests__/utils.spec.ts`
- Source: `frontend/src/lib/utils.ts` (exports `cn(...inputs: ClassValue[]): string` — `twMerge(clsx(inputs))`)

- [ ] `cn('a', 'b')` → `'a b'`.
- [ ] `cn('p-2', 'p-4')` — tailwind-merge dedupes conflicting utility classes, keeping the last → `'p-4'`.
- [ ] `cn('a', false && 'b', undefined, null, 'c')` — falsy/nullish entries from `clsx` are dropped → `'a c'`.
- [ ] `cn({ 'a': true, 'b': false })` — object form → `'a'`.
- [ ] Run `cd frontend && npm test -- lib/__tests__/utils.spec` — passing.
- [ ] Commit: `git add frontend/src/lib/__tests__/utils.spec.ts && git commit -m "test(frontend): cover lib/utils.ts"`

---

### Task 8: `components/chatbox/slashSuggestion.spec.ts`

**Files:**
- Create: `frontend/src/components/chatbox/__tests__/slashSuggestion.spec.ts`
- Source: `frontend/src/components/chatbox/slashSuggestion.ts` (exports `buildSlashItems(runAddLocalFiles: () => void): SlashItem[]` and `applySlashSelection(opts: {editor, range, command, item}): void`; also exports `createSlashSuggestion(...)`, a TipTap `Extension` factory — **out of scope for this task**, too integration-heavy to unit test cheaply; only `buildSlashItems`/`applySlashSelection` are covered)

- [ ] `buildSlashItems(fn)` returns an array with exactly one item: `{ id: 'add_local_files', titleKey: 'Add local files', run: fn }` (assert `run === fn` by reference).
- [ ] `applySlashSelection` when `command` is provided: calls `command(item)` exactly once and does **not** call `item.run()` directly, does not touch `editor`.
- [ ] `applySlashSelection` when `command` is `null` but `editor` and `range` are provided: build a minimal fake `editor` object whose shape matches what's called — `editor.chain().focus().deleteRange(range).run()` — using a chainable mock (`{ chain: () => ({ focus: () => ({ deleteRange: () => ({ run: vi.fn() }) }) }) }`, or simpler: spy via a fake object where each method returns `this`); assert the chain was invoked and `item.run()` was also called afterward.
- [ ] `applySlashSelection` when `command` is `null` and `editor`/`range` are also `null`: only `item.run()` is called, nothing throws.
- [ ] Run `cd frontend && npm test -- slashSuggestion.spec` — passing.
- [ ] Commit: `git add frontend/src/components/chatbox/__tests__/slashSuggestion.spec.ts && git commit -m "test(frontend): cover chatbox/slashSuggestion.ts pure logic"`

---

### Task 9: `composables/useAuth.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useAuth.spec.ts`
- Source: `frontend/src/composables/useAuth.ts` — exports `useAuth()` returning `{ currentUser, isAuthenticated, isLoading, authError, isAdmin, isActive, login, register, logout, logoutAll, initAuth, loadCurrentUser, refreshAuthToken, hasRole, clearError, clearAuth }`. Module-scope singleton state (`currentUser`, `isAuthenticated`, `isLoading`, `authError`) — **persists across `it()` blocks in this file**; call `clearAuth()` (or `vi.resetModules()` + re-import) at the start of each test that needs a clean slate.
- Mocks: `vi.mock('../../api/auth', ...)` for `login`/`register`/`logout`/`logoutAll`/`getCurrentUser`/`refreshToken`/`setAuthToken`/`clearAuthToken`/`storeToken`/`storeRefreshToken`/`getStoredToken`/`getStoredRefreshToken`/`clearStoredTokens`; `vi.mock('../../api/config', ...)` for `getCachedAuthProvider`.
- **Gotcha:** `useAuth()` auto-calls `initAuth()` the very first time it's invoked (module-level `if (!isAuthenticated.value && !isLoading.value) initAuth()`), and registers the `auth:logout` eventBus listener via `onMounted`/`onUnmounted` — **use the `withSetup` host-component pattern from Global Constraints** so those lifecycle hooks actually fire.

- [ ] `login(credentials)` on success: calls the mocked `apiLogin`, stores both tokens (assert the mocked `storeToken`/`storeRefreshToken`/`setAuthToken` were called with the response's tokens), sets `currentUser`/`isAuthenticated` from the response, and resolves with the response.
- [ ] `login(credentials)` on rejection: `authError.value` is set to the thrown error's `message`, `isLoading.value` ends `false`, and the promise rejects (propagates the error).
- [ ] `register(data)` — same success/failure shape as `login`, via `apiRegister`.
- [ ] `logout()` (not silent): calls the mocked `apiLogout`, then `clearAuth()` runs (assert `currentUser.value === null`, `isAuthenticated.value === false`, mocked `clearAuthToken`/`clearStoredTokens` called).
- [ ] `logout(true)` (silent): does **not** call `apiLogout`, but still clears local state.
- [ ] `logoutAll()`: calls mocked `apiLogoutAll`, then clears local state even if the API call rejects (assert `clearAuth` effects happen in the `finally`).
- [ ] `refreshAuthToken()`: with no stored refresh token (`getStoredRefreshToken` mocked to return `undefined`) → returns `false` and clears auth. With a stored refresh token and a successful `apiRefreshToken` → stores the new access token and returns `true`. With a stored refresh token and a rejecting `apiRefreshToken` → clears auth and returns `false`.
- [ ] `hasRole('admin')` / computed `isAdmin` reflect `currentUser.value.role` after a successful `login` that resolves a user with `role: 'admin'`.
- [ ] The `auth:logout` eventBus listener: with the host component mounted, `eventBus.emit('auth:logout')` triggers a silent `logout()` (assert `apiLogout` was NOT called, but `clearAuth` effects did happen).
- [ ] Run `cd frontend && npm test -- useAuth.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useAuth.spec.ts && git commit -m "test(frontend): cover composables/useAuth.ts"`

---

### Task 10: `composables/useChromePrefs.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useChromePrefs.spec.ts`
- Source: `frontend/src/composables/useChromePrefs.ts` — exports `useChromePrefs()` returning `{ browserNotificationsEnabled, soundReminderEnabled, setBrowserNotifications, setSoundReminder }`. Module-scope singleton refs initialized once at import from localStorage keys `manus-browser-notifications`/`manus-sound-reminder`.
- **Gotcha:** initial value is read from `localStorage` **at module import time** — to test the "reads persisted true from localStorage" case, seed `localStorage` then `vi.resetModules()` + dynamic `await import(...)` before asserting the initial ref value.

- [ ] Default (nothing in localStorage): `browserNotificationsEnabled.value === false`, `soundReminderEnabled.value === false`.
- [ ] With `localStorage.setItem('manus-browser-notifications', 'true')` seeded before a fresh dynamic import: initial `browserNotificationsEnabled.value === true`.
- [ ] `setSoundReminder(true)` sets `soundReminderEnabled.value` to `true` and persists it to localStorage (assert `localStorage.getItem('manus-sound-reminder') === 'true'`).
- [ ] `setBrowserNotifications(true)` when `globalThis.Notification` is undefined → sets `browserNotificationsEnabled.value` to `false` and resolves `false`.
- [ ] `setBrowserNotifications(true)` with `globalThis.Notification = { requestPermission: vi.fn().mockResolvedValue('granted') }` stubbed → resolves `true` and sets the ref `true`.
- [ ] `setBrowserNotifications(true)` with `requestPermission` resolving `'denied'` → resolves `false`, ref stays `false`.
- [ ] `setBrowserNotifications(false)` → ref set `false`, resolves `true`, without touching `Notification`.
- [ ] Run `cd frontend && npm test -- useChromePrefs.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useChromePrefs.spec.ts && git commit -m "test(frontend): cover composables/useChromePrefs.ts"`

---

### Task 11: `composables/useContextMenu.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useContextMenu.spec.ts`
- Source: `frontend/src/composables/useContextMenu.ts` — exports `useContextMenu()` returning `{ contextMenuVisible, selectedItemId, menuPosition, menuItems, targetElement, showContextMenu, hideContextMenu, handleMenuItemClick }`, plus standalone helpers `createMenuItem(key, label, options?)`, `createDangerMenuItem(key, label, options?)`, `createSubmenuItem(key, label, children, options?)`, `createSeparator()`.

- [ ] `showContextMenu(itemId, element, items, onClick, onClose)` sets `contextMenuVisible.value = true`, `selectedItemId.value = itemId`, `targetElement.value = element`, `menuItems.value = items`.
- [ ] `hideContextMenu()` resets all fields to their empty defaults (`contextMenuVisible=false`, `selectedItemId=undefined`, `menuItems=[]`, `targetElement=null`) and — if an `onClose` was registered via a prior `showContextMenu` call — invokes it with the item id that was active.
- [ ] Calling `showContextMenu` a second time while already visible implicitly calls `hideContextMenu` first (assert the *first* menu's `onClose` fires with the *first* item's id before the second menu's state is applied).
- [ ] `handleMenuItemClick(item)`: for a normal (non-disabled, no-children) item, calls the registered click handler with `(item.key, selectedItemId.value)`, then `item.action?.(selectedItemId.value)` if present, then hides the menu.
- [ ] `handleMenuItemClick(item)` with `item.disabled === true`: does nothing (no handler call, menu stays open).
- [ ] `handleMenuItemClick(item)` with `item.children?.length`: does nothing (submenu parent row — menu stays open, no handler/action call).
- [ ] `createMenuItem('k','L')` → `{ key:'k', label:'L', variant:'default' }` (icon/children absent when not passed).
- [ ] `createDangerMenuItem('k','L')` → `variant:'danger'`.
- [ ] `createSubmenuItem('k','L',[child])` → `variant:'default'`, `children:[child]`.
- [ ] `createSeparator()` → `{ key: <starts with 'separator-'>, label:'', disabled:true }`, and two calls produce different `key`s.
- [ ] Run `cd frontend && npm test -- useContextMenu.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useContextMenu.spec.ts && git commit -m "test(frontend): cover composables/useContextMenu.ts"`

---

### Task 12: `composables/useDialog.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useDialog.spec.ts`
- Source: `frontend/src/composables/useDialog.ts` — exports `useDialog()` returning `{ dialogVisible (readonly), dialogConfig, handleConfirm, handleCancel, showConfirmDialog, showInputDialog, showDeleteSessionDialog }`.
- **Gotcha:** calls `useI18n()` from `'vue-i18n'` internally for default button labels/delete-dialog copy — **use the `withSetup` host-component pattern**.

- [ ] `showConfirmDialog({title,content,onConfirm})` sets `dialogVisible.value = true`, `dialogConfig.title/content` as given, `dialogConfig.inputEnabled === false`; default `confirmText`/`cancelText` come from real i18n (`t('Confirm')`/`t('Cancel')` — assert against the actual English string since default test locale is `'en'`, matching the existing repo convention of asserting real translated text).
- [ ] `showConfirmDialog({..., confirmType: 'danger'})` → `dialogConfig.confirmType === 'danger'`; omitted → `'primary'`.
- [ ] `handleConfirm()` calls the registered `onConfirm` (awaits it if it returns a promise) then sets `dialogVisible.value = false`.
- [ ] `handleCancel()` calls the registered `onCancel` then sets `dialogVisible.value = false`; if no `onCancel` was given, just closes without throwing.
- [ ] `showInputDialog({title, initialValue, onConfirm})` sets `dialogConfig.inputEnabled === true`, `dialogConfig.inputValue === initialValue` (or `''` if omitted).
- [ ] `handleConfirm()` after `showInputDialog` calls the wrapped `onConfirm` with the **trimmed** `dialogConfig.inputValue` (set `dialogConfig.inputValue = '  x  '` before calling, assert `onConfirm` received `'x'`).
- [ ] `showDeleteSessionDialog(onConfirm)` is equivalent to `showConfirmDialog` with `confirmType: 'danger'` and the real translated delete-confirmation copy; calling `handleConfirm()` afterward invokes the passed `onConfirm`.
- [ ] Run `cd frontend && npm test -- useDialog.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useDialog.spec.ts && git commit -m "test(frontend): cover composables/useDialog.ts"`

---

### Task 13: `composables/useFilePreviewer.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useFilePreviewer.spec.ts`
- Source: `frontend/src/composables/useFilePreviewer.ts` — exports `useFilePreviewer()` returning `{ isShow, fileInfo, viewMode, fullscreenReturnViewMode, defaultViewMode, canUseSideFilePreview, showFilePreviewer, hideFilePreviewer, setViewMode, exitFullscreen, setDefaultViewMode }`. Imports the real `router` singleton from `'../router'` and `useMediaQuery` from `@vueuse/core` (mobile breakpoint `768px-1`).
- **Gotchas (both required for this file to be testable at all):**
  1. `useMediaQuery` uses `window.matchMedia`, which **jsdom does not implement** — stub it before importing: `vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })))`. To simulate "is mobile", change the mock's `matches` return per test case, or use `vi.mock('@vueuse/core', () => ({ useMediaQuery: () => ref(true/false) }))` directly — **prefer mocking `@vueuse/core`'s `useMediaQuery`**, it's simpler and avoids re-implementing the matchMedia interface.
  2. `canUseSideFilePreview` reads `router.currentRoute.value` from the real imported router singleton — use `router.push('/chat/session-123')` / `await router.isReady()` to move the real router before asserting, OR mock the whole `'../router'` module with a fake reactive `currentRoute`. **Prefer mocking `'../router'`** (`vi.mock('../../router', () => ({ router: { currentRoute: { value: <mutable object> } } }))`) — cheaper and avoids triggering the app's real lazy-loaded page imports.
  - Module-scope singleton state (`isShow`, `fileInfo`, `viewMode`, etc.) and one-time `sideGuardStarted`/`isMobileRef` guards mean **only the first call to `useFilePreviewer()` in the whole test run actually wires up the `watch`/`eventBus.on` side effects** — call `useFilePreviewer()` once per test via `vi.resetModules()` + dynamic import if a test needs the guard to re-run, or write the suite so all assertions share one `useFilePreviewer()` call's returned handles across `it()`s carefully (reset the individual refs, e.g. `viewMode.value = 'center'`, in `beforeEach` instead).

- [ ] `canUseSideFilePreview.value === false` when the mocked route path does not start with `/chat/` (e.g. `/library`).
- [ ] `canUseSideFilePreview.value === false` when route params `sessionId === 'claw'`.
- [ ] `canUseSideFilePreview.value === true` when route path starts with `/chat/` with a real (non-`'claw'`) `sessionId` param, and mobile is `false`.
- [ ] `canUseSideFilePreview.value === false` when mobile media query mock returns `true`, regardless of route.
- [ ] `showFilePreviewer(file)` with no explicit `mode`: sets `isShow.value = true`, `fileInfo.value = file`; when `defaultViewMode.value === 'center'` (default), resulting `viewMode.value === 'center'`.
- [ ] `showFilePreviewer(file, 'side')` when `canUseSideFilePreview.value === false` (mobile or wrong route): resolves to `'center'`, not `'side'` (the `resolveViewMode` guard).
- [ ] `setViewMode('fullscreen')` from `'side'`: sets `fullscreenReturnViewMode.value = 'side'` before switching; `exitFullscreen()` afterward returns `viewMode.value` back to `'side'` (or `'center'` if side became unavailable in between — assert both scenarios).
- [ ] `setViewMode('side')` when `canUseSideFilePreview.value === false`: is a no-op (`viewMode.value` unchanged).
- [ ] `hideFilePreviewer()` sets `isShow.value = false` without touching `viewMode`.
- [ ] `setDefaultViewMode('fullscreen')` then `showFilePreviewer(file)` with no explicit mode → resulting `viewMode.value === 'fullscreen'`.
- [ ] Run `cd frontend && npm test -- useFilePreviewer.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useFilePreviewer.spec.ts && git commit -m "test(frontend): cover composables/useFilePreviewer.ts"`

---

### Task 14: `composables/useI18n.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useI18n.spec.ts`
- Source: `frontend/src/composables/useI18n.ts` — exports `i18n` (a `createI18n({legacy:false, ...})` instance, also the default export) and `useLocale()` returning `{ currentLocale, setLocale }`. **Note the exported hook is named `useLocale`, not `useI18n`** — there is no exported `useI18n` function in this file (the file itself sets up the `i18n` instance consumed elsewhere via `useI18n()` from the `'vue-i18n'` package). `getBrowserLocale`/`getStoredLocale` are internal, **not exported** — test their effect only through `i18n.global.locale.value` at import and through `setLocale`.
- **Gotcha:** `i18n`'s initial `locale` is computed **once at module import time** from `localStorage.getItem('manus-locale')` (fallback: `navigator.language`). To test different initial-locale scenarios, seed `localStorage`/stub `navigator.language` **before** a `vi.resetModules()` + dynamic `await import('../useI18n')`.

- [ ] With `localStorage` empty and `navigator.language` stubbed to `'pt-BR'` (fresh module import): `i18n.global.locale.value === 'pt'`.
- [ ] Same but `navigator.language = 'zh-CN'` → `'zh'`.
- [ ] Same but `navigator.language = 'fr-FR'` (unsupported) → falls back to `'en'`.
- [ ] With `localStorage.setItem('manus-locale', 'zh')` seeded before import (regardless of `navigator.language`) → `i18n.global.locale.value === 'zh'` (stored locale wins over browser detection).
- [ ] `useLocale()` (via `withSetup`, since it's meant to be used inside a component, though it has no lifecycle hooks itself — mounting is still simplest): `setLocale('pt')` sets `i18n.global.locale.value === 'pt'`, `currentLocale.value === 'pt'`, `localStorage.getItem('manus-locale') === 'pt'`, and the `document.documentElement`'s `lang` attribute becomes `'pt'`.
- [ ] Changing `currentLocale.value` directly (not via `setLocale`) also triggers the `watch` and ends up calling `setLocale` (assert the same side effects as above happen).
- [ ] Run `cd frontend && npm test -- useI18n.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useI18n.spec.ts && git commit -m "test(frontend): cover composables/useI18n.ts"`

---

### Task 15: `composables/useResizeObserver.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useResizeObserver.spec.ts`
- Source: `frontend/src/composables/useResizeObserver.ts` — exports `useResizeObserver(targetRef, options?: {target?:'self'|'parent', callback?, property?:'width'|'height'})` returning `{ size }`. Uses `onMounted`/`onUnmounted` and the global `ResizeObserver` (not implemented by jsdom).
- **Gotchas:**
  1. Stub `ResizeObserver` globally before mounting: `class FakeResizeObserver { observe = vi.fn(); disconnect = vi.fn(); unobserve = vi.fn(); constructor(public cb: any) {} }` then `vi.stubGlobal('ResizeObserver', FakeResizeObserver)` — keep a reference to the constructed instance (e.g. capture it via a module-level array pushed in the fake constructor) so a test can manually invoke `cb()` to simulate a resize.
  2. Needs `onMounted` to fire — use the `withSetup` host-component pattern, and pass a real `ref` to a DOM element that exists in the mounted template (e.g. `setup() { const el = ref<HTMLElement|null>(null); const { size } = useResizeObserver(el); return { el, size } }`, `template: '<div ref="el"><span/></div>'` for `target:'parent'` testing via the inner span, or `<div ref="el"/>` for `target:'self'`).

- [ ] `target: 'self'`, `property: 'width'` (default `'width'`... confirm default is `'width'` per source): after mount, `size.value` reflects the target element's `offsetWidth` at mount time (jsdom's `offsetWidth` is `0` by default — stub it via `Object.defineProperty(el, 'offsetWidth', { value: 240, configurable: true })` before mount, or right after obtaining the element reference but before the observer's `updateSize` runs — adjust test structure so the stub is in place before `flushPromises()`/`nextTick()` lets `onMounted` execute).
- [ ] `target: 'parent'` (default): `size` is computed from `getParentElement(targetRef.value)`'s `offsetWidth`/`offsetHeight`, not the ref's own element.
- [ ] `property: 'height'`: uses `offsetHeight` instead of `offsetWidth`.
- [ ] Invoking the captured fake `ResizeObserver` callback (simulating a real resize) after changing the stubbed `offsetWidth`/`offsetHeight` updates `size.value` to the new value, and calls the optional `callback` option with the new size.
- [ ] Unmounting the host component (`wrapper.unmount()`) calls `disconnect()` on the fake observer instance.
- [ ] When `targetRef.value` is `null` at mount time: does not throw, `size.value` stays `0`.
- [ ] Run `cd frontend && npm test -- useResizeObserver.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useResizeObserver.spec.ts && git commit -m "test(frontend): cover composables/useResizeObserver.ts"`

---

### Task 16: `composables/useSessionFileList.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useSessionFileList.spec.ts`
- Source: `frontend/src/composables/useSessionFileList.ts` — exports `useSessionFileList()` returning `{ visible, shared, showSessionFileList, hideSessionFileList }`.

- [ ] Default state: `visible.value === false`, `shared.value === false`.
- [ ] `showSessionFileList()` (no arg) → `visible.value === true`, `shared.value === false`.
- [ ] `showSessionFileList(true)` → `visible.value === true`, `shared.value === true`.
- [ ] `hideSessionFileList()` → `visible.value === false` (does not reset `shared`).
- [ ] Run `cd frontend && npm test -- useSessionFileList.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useSessionFileList.spec.ts && git commit -m "test(frontend): cover composables/useSessionFileList.ts"`

---

### Task 17: `composables/useSessionSidebar.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useSessionSidebar.spec.ts`
- Source: `frontend/src/composables/useSessionSidebar.ts` — exports `useSessionSidebar()` returning `{ isSessionSidebarShow, toggleSessionSidebar, setSessionSidebar, showSessionSidebar, hideSessionSidebar }`. localStorage keys: `manus-session-sidebar-state` (current), `manus-left-panel-state` (legacy, migrated once at import).
- **Gotcha:** the legacy-key migration runs **once, at module import time** — test it with `vi.resetModules()` + dynamic import, seeding `localStorage` beforehand.

- [ ] Default (nothing in localStorage): `isSessionSidebarShow.value === false`.
- [ ] `localStorage.setItem('manus-session-sidebar-state', 'true')` seeded before a fresh import → `isSessionSidebarShow.value === true`.
- [ ] Legacy migration: with only `localStorage.setItem('manus-left-panel-state', 'true')` seeded (no new key) before a fresh import → `isSessionSidebarShow.value === true`, AND after import `localStorage.getItem('manus-session-sidebar-state') === 'true'` while `localStorage.getItem('manus-left-panel-state') === null` (migrated + legacy key removed).
- [ ] `toggleSessionSidebar()` flips the boolean each call.
- [ ] `setSessionSidebar(true)` / `showSessionSidebar()` / `hideSessionSidebar()` set the expected values, and each change persists to `localStorage.getItem('manus-session-sidebar-state')` (the `watch` side effect).
- [ ] Run `cd frontend && npm test -- useSessionSidebar.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useSessionSidebar.spec.ts && git commit -m "test(frontend): cover composables/useSessionSidebar.ts"`

---

### Task 18: `composables/useSettingsDialog.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useSettingsDialog.spec.ts`
- Source: `frontend/src/composables/useSettingsDialog.ts` — exports `useSettingsDialog()` returning `{ isSettingsDialogOpen, defaultTab, openSettingsDialog, closeSettingsDialog, toggleSettingsDialog, setDefaultTab }`. `SettingsTabId = 'general'|'account'|'shortcuts'|'personalization'|'help'`.

- [ ] `openSettingsDialog()` (no arg) → `isSettingsDialogOpen.value === true`, `defaultTab.value` unchanged from whatever it was.
- [ ] `openSettingsDialog('account')` → `defaultTab.value === 'account'`, dialog open.
- [ ] `openSettingsDialog('settings')` (the special legacy-alias value) → `defaultTab.value === 'general'`.
- [ ] `openSettingsDialog('not-a-real-tab')` → dialog still opens (`isSettingsDialogOpen.value === true`) but `defaultTab.value` is left unchanged (falls through every branch).
- [ ] `closeSettingsDialog()` → `isSettingsDialogOpen.value === false`.
- [ ] `toggleSettingsDialog()` flips the boolean.
- [ ] `setDefaultTab('help')` sets `defaultTab.value === 'help'` without changing `isSettingsDialogOpen`.
- [ ] Run `cd frontend && npm test -- useSettingsDialog.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useSettingsDialog.spec.ts && git commit -m "test(frontend): cover composables/useSettingsDialog.ts"`

---

### Task 19: `composables/useTime.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useTime.spec.ts`
- Source: `frontend/src/composables/useTime.ts` — exports `useRelativeTime()` returning `{ relativeTime: ComputedRef<(timestamp:number)=>string> }` and `useCustomTime()` returning `{ customTime: ComputedRef<(timestamp:number)=>string> }`. Both set a `window.setInterval` every 60000ms via `onMounted`, cleared in `onUnmounted`; `useCustomTime` additionally calls `useI18n()`.
- **Gotcha:** both need the `withSetup` host-component pattern (lifecycle hooks; `useCustomTime` also needs the i18n plugin). Use `vi.useFakeTimers()` to control/advance the 60s tick without a real wait.

- [ ] `useRelativeTime().relativeTime.value` is a function; calling it with a timestamp delegates to `formatRelativeTime` (assert output matches calling `formatRelativeTime` directly with the same timestamp under the same mocked "now").
- [ ] After `vi.advanceTimersByTimeAsync(60000)`, the composable's internal `currentTime` re-triggers (assert the returned function, called before vs. after the tick with a fixed relative timestamp close to a boundary — e.g. 59s vs 61s ago relative to the *original* mount time — crosses from `"Just now"` to `"1 minutes ago"`-style output, proving recomputation happened, not merely that the function is stable).
- [ ] Unmounting the host component clears the interval (spy on `clearInterval`, assert it was called on unmount).
- [ ] `useCustomTime().customTime.value(timestamp)` delegates to `formatCustomTime(timestamp, t, locale.value)` — assert output matches calling `formatCustomTime` directly with the same args.
- [ ] Run `cd frontend && npm test -- useTime.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useTime.spec.ts && git commit -m "test(frontend): cover composables/useTime.ts"`

---

### Task 20: `composables/useTool.spec.ts`

**Files:**
- Create: `frontend/src/composables/__tests__/useTool.spec.ts`
- Source: `frontend/src/composables/useTool.ts` — exports `useToolInfo(tool?: Ref<ToolContent | undefined>)` returning `{ toolInfo: ComputedRef<{icon,name,function,functionArg,view} | null> }`. **Exported name is `useToolInfo`, not `useTool`** (file name is `useTool.ts` but there is no `useTool` export). Reads from `constants/tool.ts`'s `TOOL_ICON_MAP`/`TOOL_NAME_MAP`/`TOOL_FUNCTION_MAP`/`TOOL_FUNCTION_ARG_MAP`/`TOOL_COMPONENT_MAP`, and calls `useI18n()` — **use `withSetup`**.

- [ ] `useToolInfo(undefined)` and `useToolInfo(ref(undefined))` both → `toolInfo.value === null`.
- [ ] For a tool whose `function` starts with `'mcp_'` (e.g. `function: 'mcp_search'`): `toolInfo.value.function === 'search'` (prefix stripped), `icon === TOOL_ICON_MAP['mcp']`, `name === t(TOOL_NAME_MAP['mcp'] ?? 'MCP Tool')`.
  - With `args: { query: 'short string' }` → `functionArg === 'short string'` (first arg value, string, `<50` chars).
  - With `args: { data: { deeply: 'nested' } }` (non-string first value) → `functionArg === JSON.stringify(...).substring(0,30) + '...'`.
  - With `args: {}` → `functionArg === ''`.
- [ ] For a non-MCP tool: read one real entry from `TOOL_FUNCTION_ARG_MAP`/`TOOL_ICON_MAP`/`TOOL_NAME_MAP`/`TOOL_FUNCTION_MAP` (open `frontend/src/constants/tool.ts` first to pick one real `tool.name`/`tool.function` pair that exists in the maps) and assert `toolInfo.value` matches those map entries exactly for a fixture `ToolContent` using that pair.
  - Specifically test the `file` path-stripping branch: when `TOOL_FUNCTION_ARG_MAP[tool.function] === 'file'` and `args.file === '/home/ubuntu/report.txt'` → `functionArg === 'report.txt'` (leading `/home/ubuntu/` stripped).
- [ ] For a tool `name`/`function` with no matching map entry: `icon === null`, `name === ''` (falls back to `t('')`), `function` falls back to the raw `tool.function` string untranslated.
- [ ] Run `cd frontend && npm test -- useTool.spec` — passing.
- [ ] Commit: `git add frontend/src/composables/__tests__/useTool.spec.ts && git commit -m "test(frontend): cover composables/useTool.ts (useToolInfo)"`

---

### Task 21: `composables/useAgentEvents.events.spec.ts` (expansion)

**Files:**
- Create: `frontend/src/composables/__tests__/useAgentEvents.events.spec.ts`
- Source: `frontend/src/composables/useAgentEvents.ts` — exports `useAgentEvents(state: AgentEventState, options?: AgentEventOptions)` returning `{ handleEvent }`. No lifecycle hooks, no `useI18n()` hook call (reads `i18n.global.t` directly) — **no `withSetup` needed**, call it bare exactly like the existing sibling spec.
- **Pattern reference (read first, copy its `makeState`/fixture style exactly):** `frontend/src/composables/__tests__/useAgentEvents.logs.spec.ts` — this new file covers everything that spec does NOT: the main `message`/`tool`/`step`/`error`/`title`/`plan`/`wait`/`done` branches that build `state.messages`, not the `logs` ring buffer.

- [ ] `message` event, `role:'assistant'` with non-empty trimmed `content`: pushes `{type:'assistant', content: {...messageData}}` onto `messages.value`.
- [ ] `message` event, `role:'assistant'` with blank/whitespace-only `content` and no attachments: pushes nothing.
- [ ] `message` event, `role:'assistant'` with blank `content` but non-empty `attachments`: pushes exactly one `{type:'attachments', content:{...messageData}}` entry, not an `'assistant'` entry.
- [ ] `message` event, `role:'user'`: pushes `{type:'user', content: {...messageData, attachments: <as given or undefined if empty>}}`.
- [ ] `message` event with non-empty `attachments` on any role that also produces a primary bubble: pushes **two** entries — the primary one, then a trailing `{type:'attachments', ...}`.
- [ ] `tool` event, first tool seen (no `lastTool` yet, no running step): pushes `{type:'tool', content: toolData}` onto `messages.value` and sets `state.lastTool.value` to it.
- [ ] `tool` event with the same `tool_call_id` as `lastTool.value`: does **not** push a new message; instead `Object.assign`s the update onto the existing `lastTool.value` object (assert `messages.value` length unchanged, and the *object identity* in `messages.value` reflects the merged fields).
- [ ] `tool` event while the last pushed message is a `'step'` with `status:'running'`: the tool is appended to that step's `content.tools` array instead of being pushed as its own top-level message.
- [ ] `tool` event with `name !== 'message'`: sets `state.lastNoMessageTool.value` and calls `options.onToolActivity` with the tool content. A tool event with `name === 'message'` does neither.
- [ ] `step` event, `status:'running'`: pushes `{type:'step', content:{...stepData, tools:[]}}`.
- [ ] `step` event, `status:'completed'`: does not push a new message; mutates the most recent `'step'` message's `content.status` to `'completed'` in place.
- [ ] `step` event, `status:'failed'`: calls `options.onStreamError`, does not push or mutate a step message.
- [ ] `error` event: calls `options.onStreamError`, pushes `{type:'assistant', content:{content: errorData.error, timestamp: errorData.timestamp}}`.
- [ ] `title` event: sets `state.title.value = titleData.title`.
- [ ] `plan` event: sets `state.plan.value = planData` (whole object, by reference or deep-equal).
- [ ] `wait` / `done` events: no-op on `messages`/`title`/`plan` (per the source comments), but still update `state.lastEventId.value` to the event's `event_id` (shared behavior at the bottom of `handleEvent`, applies to every event type — verify once here for `wait`/`done` specifically since the main branches above already implicitly cover it for the others).
- [ ] `status_update` / `terminal_update` / `file_update` events: `handleEvent` returns immediately — `messages.value` untouched, `lastEventId.value` **also untouched** (these three are filtered before the trailing `lastEventId` assignment — confirm this from the source's early `return` and assert it, don't assume).
- [ ] Run `cd frontend && npm test -- useAgentEvents` — both the existing `.logs.spec.ts` and this new file pass.
- [ ] Commit: `git add frontend/src/composables/__tests__/useAgentEvents.events.spec.ts && git commit -m "test(frontend): expand useAgentEvents coverage to main event-type branching"`

---

### Task 22: `api/client.spec.ts`

**Files:**
- Create: `frontend/src/api/__tests__/client.spec.ts`
- Source: `frontend/src/api/client.ts` — exports `apiClient` (a live `axios.create(...)` instance with request/response interceptors already attached), `API_CONFIG`, `BASE_URL`, and TS types `ApiResponse<T>`/`ApiError`. Imports `getStoredToken`/`getStoredRefreshToken`/`storeToken`/`storeRefreshToken`/`clearStoredTokens` from `./auth` (real localStorage-backed functions — **do not mock `./auth`, call the real ones against jsdom's `localStorage`**, it's simpler and more realistic) and `eventBus` from `../utils/eventBus`.
- **Key technique — do NOT mock `axios` or `./client` wholesale.** `apiClient` is the exact object under test, already carrying its interceptors. Instead, override its transport at the adapter level so the interceptors still execute around it:
  ```ts
  import { apiClient } from '../client'
  const adapterMock = vi.fn()
  beforeEach(() => { apiClient.defaults.adapter = adapterMock })
  ```
  Each test sets `adapterMock.mockResolvedValueOnce({ data: {...}, status: 200, headers: {}, config: {} as any })` or `adapterMock.mockRejectedValueOnce(<AxiosError-shaped object with .response/.config>)` per call. Construct AxiosError-shaped rejections as plain objects with `{ response: { status, data }, config: <the same config object the adapter received>, isAxiosError: true }` — axios's own response interceptor only inspects `.response`/`.config`, it does not require a real `AxiosError` class instance for this codebase's interceptor logic to run correctly.

- [ ] Request interceptor: with `storeToken('abc')` called first (real function, writes to localStorage), an outgoing request through `apiClient.get('/whatever')` (adapter mocked to resolve immediately) results in the adapter having been called with `config.headers.Authorization === 'Bearer abc'`.
- [ ] With no stored token (`clearStoredTokens()` first): outgoing request has no `Authorization` header set by the interceptor.
- [ ] Response interceptor, success envelope: adapter resolves `{ data: { code: 0, msg: 'ok', data: {foo:1} }, status:200, ... }` → `apiClient.get(...)` resolves with the **full axios response** (`response.data.data.foo === 1`) — the interceptor passes non-error envelopes through unchanged, it does not unwrap `data.data` itself (confirm this from source: `if (code !== 0) reject; return response;` — the caller still receives `response.data.data`, not top-level unwrap).
- [ ] Response interceptor, business-error envelope: adapter resolves `{ data: { code: 42, msg: 'bad thing' }, status:200 }` → `apiClient.get(...)` **rejects** with `{code:42, message:'bad thing', details: <the full response.data>}`.
- [ ] 401 single-flight refresh: mock the adapter so the **first** call to any URL other than `/auth/refresh` rejects with a 401 AxiosError-shaped object; the **next** call (triggered internally when the interceptor calls `apiClient.post('/auth/refresh', ...)`) resolves with `{ data: { data: { access_token:'new', refresh_token:'newr' } } }`; a **third** adapter call (the automatic retry of the original request) resolves success. Assert: `apiClient.get('/foo')` ultimately resolves (not rejects), `storeToken`/localStorage now holds `'new'`, and the retried request's `Authorization` header is `'Bearer new'`.
- [ ] Concurrent 401s: fire two `apiClient.get(...)` calls back-to-back (both hit 401 before the refresh resolves) — assert the adapter's `/auth/refresh` endpoint was invoked only **once** (single-flight queue), and both original calls eventually resolve once the shared refresh completes.
- [ ] Refresh failure: adapter's `/auth/refresh` call itself rejects (e.g. 401) → the original request ultimately rejects, `localStorage` no longer holds tokens (`clearStoredTokens` ran), and an `'auth:logout'` event was emitted on `eventBus` (register a spy via `eventBus.on('auth:logout', spy)` beforehand).
- [ ] A request whose config carries `__isRefreshRequest: true` and gets a non-2xx response skips the retry-loop entirely and rejects directly with `{code, message:'Token refresh failed', details}` (prevents infinite refresh loops) — construct this directly by calling `apiClient.post('/auth/refresh', {}, { __isRefreshRequest: true } as any)` with the adapter mocked to 401.
- [ ] Generic non-401 error (e.g. 500, or a network error with `error.request` but no `error.response`): rejects with a shaped `ApiError` (`code`, `message` derived from `error.response.statusText`/`'Network error, please check your connection'` for the no-response case).
- [ ] Run `cd frontend && npm test -- api/__tests__/client.spec` — passing.
- [ ] Commit: `git add frontend/src/api/__tests__/client.spec.ts && git commit -m "test(frontend): cover api/client.ts interceptors and refresh queue"`

---

### Task 23: `api/chatWs.spec.ts`

**Files:**
- Create: `frontend/src/api/__tests__/chatWs.spec.ts`
- Source: `frontend/src/api/chatWs.ts` — the `ChatWebSocket` class itself is **not exported**; the only public entry point is `getChatWebSocket(): ChatWebSocket` (module-level singleton, `connect()`s immediately on first creation) plus the exported constants `CHAT_WS_PROTOCOL_VERSION`/`CHAT_WS_REQUEST_TIMEOUT_MS` and the `ChatWSServerMessage` type. Public instance methods reachable for testing: `setHandlers(sessionId, handlers)`, `clearHandlers(sessionId)`, `joinSession(sessionId, lastEventId?)`, `leaveSession(sessionId?)`, `chat(params)`, `stopSession(sessionId)`, `destroy()`.
- **Required fake WebSocket** (place at top of the spec file):
  ```ts
  class FakeWebSocket {
    static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
    readyState = FakeWebSocket.CONNECTING;
    onopen: (() => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    sent: string[] = [];
    constructor(public url: string) { FakeWebSocket.instances.push(this) }
    static instances: FakeWebSocket[] = []
    send(data: string) { this.sent.push(data) }
    close() { this.readyState = FakeWebSocket.CLOSED; this.onclose?.() }
    /** test helper, not part of the real WebSocket API */
    open() { this.readyState = FakeWebSocket.OPEN; this.onopen?.() }
    /** test helper */
    receive(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }) }
  }
  ```
  `vi.stubGlobal('WebSocket', FakeWebSocket)` in `beforeEach`, and reset `FakeWebSocket.instances = []` + `vi.resetModules()` before each test that needs a fresh singleton (`getChatWebSocket()` caches module-level `singleton` — a fresh `await import('../chatWs')` per test, or per logical group, is required to avoid state bleeding between tests; group related assertions within one test where practical instead of re-importing for every single `it()`).
- **Timing:** use `vi.useFakeTimers()` for the reconnect-backoff and request-timeout assertions (`vi.advanceTimersByTimeAsync(ms)`), `afterEach(() => vi.useRealTimers())`.

- [ ] `getChatWebSocket()` constructs exactly one `FakeWebSocket` (assert `FakeWebSocket.instances.length === 1`) pointed at a URL derived from `BASE_URL` with `http`→`ws` and `/ws/chat` appended (import `BASE_URL` from `../client` to build the expected string).
- [ ] Calling `getChatWebSocket()` twice returns the **same** instance (singleton) and does not construct a second `FakeWebSocket`.
- [ ] `joinSession('s1')`: call it, then `instances[0].open()` to simulate connection — assert a `'join_session'` frame was sent (`JSON.parse(instances[0].sent[last])`) with `session_id:'s1'`, `type:'join_session'`, and the envelope fields `id`/`timestamp`/`version:2`/`conn_id` present; then `instances[0].receive({type:'joined', session_id:'s1', request_id: <the sent id>})` — the `joinSession(...)` promise resolves.
- [ ] `joinSession` while already joined to a **different** session: sends a `'leave_session'` frame for the old session before the new `'join_session'` request.
- [ ] Request timeout: `joinSession('s1')` with the fake socket opened but never receiving a `'joined'`/error reply — after `vi.advanceTimersByTimeAsync(CHAT_WS_REQUEST_TIMEOUT_MS)`, the promise **rejects** with an error mentioning `'timed out'`.
- [ ] `setHandlers('s1', { onEvent })` + a server `{type:'event', session_id:'s1', event:'message', data:{...}}` message → `onEvent` is called with `{event:'message', data:{...}}`.
- [ ] A `{type:'event', session_id:'s1', event:'status_update', data:{agent_status:'running',...}}` message calls **both** `onStatusUpdate('running')` and `onEvent({event:'status_update', data:...})`.
- [ ] `{type:'error', session_id:'s1', error:'boom', code:7}` with no matching pending request (unsolicited server error) → calls `handlers.get('s1').onError('boom', 7)`.
- [ ] `{type:'stream_end', session_id:'s1'}` → calls `onStreamEnd`.
- [ ] `clearHandlers('s1')` then a subsequent event for `'s1'` → no handler methods are called (no throw either).
- [ ] Reconnect: simulate `instances[0].close()` (triggers `onclose` → `scheduleReconnect`); `vi.advanceTimersByTimeAsync(1000)` (initial `reconnectDelay`) → a **second** `FakeWebSocket` instance is constructed (assert `instances.length === 2`); opening it (`instances[1].open()`) re-sends a `'join_session'` frame for whatever session was joined before the disconnect (re-join behavior).
- [ ] Exponential backoff: two consecutive disconnects before ever reconnecting successfully double the delay each time (assert via inspecting how much fake time must elapse before the next `FakeWebSocket` appears: 1000ms then 2000ms), capped at 30000ms (not required to prove the cap exactly, just the doubling).
- [ ] `chat({sessionId, message})` when not currently joined to that session: joins first (assert a `'join_session'` frame precedes the `'chat'` frame), then sends `'chat'` and awaits its `'ack'`.
- [ ] `stopSession('s1')`: sends `'stop_session'`, resolves once a `{type:'stopped', session_id:'s1', request_id:<matching>}` arrives.
- [ ] `destroy()`: closes the underlying socket, and any pending `joinSession`/`chat` promise in flight at that moment rejects with an error mentioning `'destroyed'`.
- [ ] Run `cd frontend && npm test -- api/__tests__/chatWs.spec` — passing.
- [ ] Commit: `git add frontend/src/api/__tests__/chatWs.spec.ts && git commit -m "test(frontend): cover api/chatWs.ts protocol, reconnect, and request/ack flow"`

---

### Task 24: `api/config.spec.ts`

**Files:**
- Create: `frontend/src/api/__tests__/config.spec.ts`
- Source: `frontend/src/api/config.ts` — exports `getClientConfig()`, `getCachedClientConfig()`, `getCachedAuthProvider()`. Module-level cache: `clientConfigCache`/`isClientConfigLoaded` — **persist across calls within a module instance**; use `vi.resetModules()` + dynamic import per test that needs a fresh cache state.
- Mock: `vi.mock('../client', () => ({ apiClient: { get: vi.fn() } }))` (only `apiClient.get` is used by this file).

- [ ] `getClientConfig()` calls `apiClient.get('/config/frontend')` and returns `response.data.data` (unwraps one level — confirm this differs from `client.ts`'s own interceptor, which does NOT unwrap; `config.ts` does the unwrap itself on top of that).
- [ ] `getCachedClientConfig()` first call: calls `apiClient.get` once, returns the config.
- [ ] `getCachedClientConfig()` second call (same module instance, no reset): does **not** call `apiClient.get` again, returns the same cached object (reference-equal is fine to assert, or deep-equal).
- [ ] `getCachedClientConfig()` when the underlying fetch rejects: returns `null` (does not throw), and a **subsequent** call still does not retry (cache is set to "loaded" even on failure — assert `apiClient.get` was called only once across both calls).
- [ ] `getCachedAuthProvider()` returns `clientConfig.auth_provider` when the cached config loaded successfully.
- [ ] `getCachedAuthProvider()` returns `null` when the cached config is `null` (fetch failed) or when `auth_provider` itself is falsy.
- [ ] Run `cd frontend && npm test -- api/__tests__/config.spec` — passing.
- [ ] Commit: `git add frontend/src/api/__tests__/config.spec.ts && git commit -m "test(frontend): cover api/config.ts caching behavior"`

---

### Task 25: `router/index.spec.ts`

**Files:**
- Create: `frontend/src/router/__tests__/index.spec.ts`
- Source: `frontend/src/router/index.ts` — exports the real `router` singleton (`createRouter(...)` with a `beforeEach` guard already registered inline — **not separately exported/callable**, so this task tests the guard's observable effect via real navigation on the real `router`, not by re-implementing the guard logic). Guard depends on `getStoredToken` (`../api/auth`) and `getCachedClientConfig` (`../api/config`) — mock both.
- **Note the exact bypass condition from source** (do not assume only `'none'` bypasses): `if (authProvider === 'none' || authProvider === null) { next(); return }` — a `getCachedClientConfig` mock resolving `null`, or resolving an object with `auth_provider: null`/absent, **also** bypasses the auth requirement.

- [ ] Mock `getCachedClientConfig` to resolve `{ auth_provider: 'none', ... }`, `getStoredToken` to return `null`: `await router.push('/library')` then `await router.isReady()` — lands on `/library` (not redirected), `router.currentRoute.value.path === '/library'`.
- [ ] Mock `getCachedClientConfig` to resolve `null` (fetch failed): same as above, `requiresAuth` routes are also bypassed (the `authProvider === null` branch).
- [ ] Mock `getCachedClientConfig` to resolve `{ auth_provider: 'password' }`, `getStoredToken` to return `null`: `router.push('/library')` → redirected to `/login` with `router.currentRoute.value.query.redirect` equal to the originally-requested path.
- [ ] Same but `getStoredToken` returns `'sometoken'`: navigation to `/library` succeeds (not redirected).
- [ ] Navigating directly to `/login` with `auth_provider: 'none'`: redirected to `/`.
- [ ] Navigating directly to `/login` with a real provider and a stored token present: redirected to `/`.
- [ ] Navigating directly to `/login` with a real provider and **no** stored token: stays on `/login` (no redirect loop).
- [ ] Navigating to `/share/:sessionId` (a route with no `requiresAuth` meta) with no token and a real auth provider: succeeds without redirect (public route).
- [ ] Run `cd frontend && npm test -- router/__tests__/index.spec` — passing. **If real navigation triggers problematic dynamic imports of heavy page components (Monaco/NoVNC) that fail under jsdom**, fall back to asserting only against the top-level `MainLayout.vue`/`LoginPage.vue`/`ShareLayout.vue` routes (which are what actually gets awaited during guard resolution) rather than deeper nested children, and note the concrete failure in the task's completion report so the reviewer can confirm the fallback was necessary, not a shortcut.
- [ ] Commit: `git add frontend/src/router/__tests__/index.spec.ts && git commit -m "test(frontend): cover router auth guard"`

---

## Final Verification (after all 25 tasks)

1. `cd frontend && npm run test` — full suite (21 pre-existing + 25 new = 46 spec files) green.
2. `cd frontend && npm run test:coverage` — confirm `utils/`, `composables/`, `api/client.ts`, `api/chatWs.ts`, `api/config.ts`, `router/index.ts` show high line coverage in the printed table.
3. `cd frontend && npm run type-check && npm run lint` — clean.
4. Manually re-read `.github/workflows/frontend-tests.yml` once more against the final `package.json` scripts to confirm the CI steps still match exactly.
5. Final whole-branch code review per `superpowers:subagent-driven-development`.
6. Commit summarizing scope covered / explicitly deferred, test + coverage results, per this session's commit-message discipline, trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
