# User Profile Photo (Avatar)

**Date:** 2026-08-06
**Status:** approved, not yet implemented
**Scope:** Backend (new field + 3 endpoints) + Frontend (crop UI, shared avatar component, 4 call sites)

## Problem

The user's avatar is always a solid-color circle showing the first letter of
their `fullname`. This exact markup (`avatarLetter` computed +
`rounded-full` div) is duplicated in four places:

- `frontend/src/components/settings/AccountSettings.vue`
- `frontend/src/components/settings/SettingsTabs.vue`
- `frontend/src/components/UserMenu.vue`
- `frontend/src/components/SessionSidebar.vue`

There is no photo upload anywhere in the codebase — no field on `User`, no
avatar-serving endpoint, no frontend upload UI. `docs/backlog/paridade-manus.md`
doesn't mention it either; this is new scope, not a deferred backlog item.

## Goal

Let a user upload, crop, and remove a profile photo from Settings → Account.
Every place that currently renders the initials circle shows the photo when
one is set, falling back to initials otherwise.

### Success criteria

- User can pick an image, crop it to a circle (drag to pan, slider to zoom),
  and save it as their avatar from Settings → Account.
- The photo appears immediately in all four avatar locations after upload,
  and reverts to initials immediately after removal.
- Photo persists across reload/relogin and is visible to other authenticated
  users (e.g. wherever another user's name/avatar might show up), not just
  the owner.
- Non-image or oversized uploads are rejected with a clear error, both
  client-side (before the crop step) and server-side (defense in depth).

### Non-goals

- Image rotation, multiple photos, or photo history.
- Content moderation of uploaded images.
- Changing how existing chat-attachment file upload/signed-URL flows work.

## Storage & serving approach

Existing generic file infrastructure (`FileService` → GridFS via
`GridFSFileStorage`) already handles arbitrary blob storage with per-owner
metadata. Reusing it for avatars avoids adding a second storage mechanism.

What's new is *serving*: the existing `GET /files/{id}` /
`GET /files/{id}/download` paths are built around chat attachments and rely
on signed URLs capped at 30 minutes (`FileService.create_signed_url`) — fine
for a chat bubble, wrong for something rendered in the sidebar on every page
load. A profile photo needs a stable, non-expiring URL any authenticated
user can load.

**Decision:** a dedicated `GET /auth/avatar/{user_id}` endpoint, gated only
by `get_current_user` (any authenticated session, not owner-restricted —
avatars are meant to be seen by other users, same as a display name). It
looks up the target user's `avatar_file_id` and streams the GridFS blob
directly (`FileService.download_file(file_id)` with no `user_id` argument,
same "skip ownership check" call shape the existing public/signed
`GET /files/{id}` route already uses — not a new access pattern).

`UserResponse` gains `avatar_url: Optional[str]`, pre-built by the backend
as `/api/v1/auth/avatar/{user_id}?v=<updated_at unix ts>`. The `v` query
param is a cache-buster: browsers would otherwise keep serving a stale
cached image after a change, since the path itself never changes. `null`
when the user has no avatar — the frontend never has to guess or issue a
request that's expected to 404.

## Backend changes

- `domain/models/user.py`: `User.avatar_file_id: Optional[str] = None`.
- `infrastructure/models/documents.py`: matching field on `UserDocument`.
- `interfaces/schemas/auth.py`: `UserResponse.avatar_url: Optional[str]`,
  computed in `UserResponse.from_domain` (needs the request's base URL or a
  configured public base — follow whatever pattern `FileInfoResponse` /
  `enrich_with_file_url` already use for building absolute file URLs).
- `application/services/auth_service.py`: two new methods —
  - `change_avatar(user_id, file_data, filename, content_type) -> User`:
    validates `content_type` against an image whitelist
    (`image/jpeg`, `image/png`, `image/webp`) and size (≤5MB) before calling
    `FileService.upload_file`; deletes the previous `avatar_file_id`'s file
    (if any) via `FileService.delete_file` *after* the new upload succeeds
    (so a failed upload never leaves the user with no photo); updates and
    saves the user record.
  - `remove_avatar(user_id) -> User`: deletes the current avatar file (if
    any), clears `avatar_file_id`, saves.
- `interfaces/api/auth_routes.py`:
  - `POST /auth/avatar` (multipart `UploadFile`) → `AuthService.change_avatar`,
    returns `UserResponse`.
  - `DELETE /auth/avatar` → `AuthService.remove_avatar`, returns `UserResponse`.
  - `GET /auth/avatar/{user_id}` → looks up the user, 404 if not found or no
    `avatar_file_id`, otherwise streams the file (reuse the same
    `StreamingResponse` + `Content-Disposition`-free pattern `file_routes.py`
    uses for inline image display, plus a long `Cache-Control` header since
    the URL is versioned by the `v` query param).

## Frontend changes

- **Crop editor** (new, no new dependency): a dialog component
  (`components/settings/AvatarCropDialog.vue` or similar) that loads the
  picked file into an `<img>`/`<canvas>`, overlays a fixed circular guide,
  and supports drag-to-pan plus a zoom slider. "Save" renders the visible
  crop region into an offscreen 512×512 canvas and exports it via
  `canvas.toBlob(..., 'image/jpeg', 0.9)`. The pure geometry (given
  image natural size, pan offset, zoom, and guide radius, compute the
  source rectangle to draw) is extracted into a standalone function so it's
  unit-testable without mounting the component or touching the DOM.
- **`api/auth.ts`**: `uploadAvatar(blob: Blob): Promise<User>` (multipart
  POST `/auth/avatar`), `removeAvatar(): Promise<User>` (DELETE
  `/auth/avatar`).
- **New shared `components/UserAvatar.vue`**: props `avatarUrl?: string,
  fallbackLetter: string, size` (or a Tailwind size class). Renders an
  `<img>` when `avatarUrl` is set, with an `@error` handler that falls back
  to the existing initials-circle markup (covers the rare case of a stale
  `avatar_url` pointing at a since-deleted file); renders the initials
  circle directly when `avatarUrl` is `null`/undefined.
- Swap `UserAvatar` into the four existing call sites listed under
  "Problem", removing the duplicated `avatarLetter` div markup from each
  (each keeps its own sizing, `UserAvatar` takes a size prop).
- **`AccountSettings.vue`**: "Change photo" / "Remove photo" controls next
  to the avatar, wiring file-picker → crop dialog → `uploadAvatar` /
  `removeAvatar`, updating `currentUser` (via `useAuth`'s existing
  `loadCurrentUser()`, same pattern `changeFullname` already uses) so every
  `UserAvatar` instance on screen updates immediately.
- i18n keys added to `en.ts`, `pt.ts`, `zh.ts` for the new labels/errors
  (invalid file type, file too large, upload failed, "Change photo",
  "Remove photo", crop dialog title/buttons).

## Validation & error handling

- Client-side, before opening the crop dialog: reject non-image files and
  files over 5MB with a toast, matching the existing `showErrorToast`
  pattern used elsewhere in `AccountSettings.vue`.
- Server-side, in `change_avatar`: re-check `content_type` and byte size
  (defense in depth — the crop step normally produces a small JPEG, but the
  endpoint must not trust the client). Reject with a 400 via the existing
  `BadRequestError`/`APIException` pattern other auth routes use.
- Upload failure (network error, server rejection): crop dialog stays open
  with an inline error, matching how `ChatBoxFiles.vue`'s optimistic upload
  shows a failed state with retry — reuse that visual language, not a new
  pattern.

## Testing

- Backend unit tests (`backend/tests/test_avatar.py` or added to
  `test_auth_routes.py`): mime/size validation rejects bad input; a
  successful `change_avatar` deletes the previous file only after the new
  upload succeeds; `remove_avatar` clears the field and deletes the file;
  `GET /auth/avatar/{id}` returns 401 unauthenticated, 404 for a user with
  no avatar, and 200 with the image bytes for an authenticated request to
  *another* user's avatar (not just the owner's).
- Frontend: the extracted crop-geometry function gets a focused unit spec
  (pure input/output, no DOM); `npm run test && npm run type-check && npm
  run lint && npm run build` all pass same as any other change here.

## Open questions / risks

- `UserResponse.from_domain` needs a base URL to build the absolute
  `avatar_url`. Check how `FileInfoResponse`/`enrich_with_file_url` already
  solve this (likely `settings`-driven public base URL or built from the
  incoming request) and follow the same approach rather than inventing a
  second one — this is an implementation detail to confirm while writing
  the plan, not a design fork.
