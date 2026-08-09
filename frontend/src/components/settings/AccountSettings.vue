<template>
  <div class="space-y-6 w-full">
    <div class="space-y-4">
      <div class="flex gap-4 items-center">
        <div class="flex items-center gap-4 flex-1 min-w-0">
          <div class="flex flex-col items-start gap-2">
            <UserAvatar :avatar-url="currentUser?.avatar_url" :fallback-letter="avatarLetter" :size="64" />
            <div class="flex gap-2">
              <button
                type="button"
                class="text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] clickable"
                @click="triggerFilePicker"
              >
                {{ t('Change photo') }}
              </button>
              <button
                v-if="currentUser?.avatar_url"
                type="button"
                class="text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] clickable"
                @click="handleRemoveAvatar"
              >
                {{ t('Remove photo') }}
              </button>
            </div>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              class="hidden"
              @change="onFilePicked"
            >
          </div>

          <AvatarCropDialog
            v-if="pickedFile"
            :file="pickedFile"
            @saved="handleCropSaved"
            @cancel="pickedFile = null"
          />
          <div class="flex-1 min-w-0 space-y-1">
            <div class="text-[var(--text-tertiary)] text-[13px] leading-[18px] flex items-center gap-1">
              {{ t('Full name') }}
            </div>
            <div
              class="group rounded-[8px] overflow-hidden text-sm text-[var(--text-primary)] bg-[var(--fill-tsp-white-main)] py-2 px-3 w-full sm:w-[280px] flex items-center gap-2 focus-within:ring-[1.5px] focus-within:ring-[var(--border-input-active)]"
            >
              <input
                v-model="localFullname"
                maxlength="20"
                class="h-full min-w-0 flex-1 bg-transparent outline-none placeholder:text-[var(--text-disable)]"
                :placeholder="t('Unknown User')"
                @blur="handleFullnameSubmit"
                @keyup.enter="handleFullnameSubmit"
              >
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="w-full h-[1px] bg-[var(--border-main)]" />

    <div class="space-y-6">
      <div class="rounded-[12px] p-[12px] -m-[12px]">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex flex-col items-start justify-center flex-1 min-w-0">
            <span class="text-sm font-medium text-[var(--text-primary)]">{{ t('Email') }}</span>
            <div class="text-[13px] text-[var(--text-tertiary)] leading-[18px] w-full">
              {{ currentUser?.email || t('No email') }}
            </div>
          </div>
        </div>
      </div>

      <div class="rounded-[12px] p-[12px] -m-[12px]">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex flex-col items-start justify-center flex-1 min-w-0">
            <span class="text-sm font-medium text-[var(--text-primary)]">{{ t('User ID') }}</span>
            <div class="text-[13px] text-[var(--text-tertiary)] leading-[18px] w-full truncate">
              {{ currentUser?.id || '—' }}
            </div>
          </div>
          <button
            type="button"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 outline outline-1 -outline-offset-1 hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-primary)] outline-[var(--border-btn-main)] bg-transparent h-[32px]"
            @click="copyUserId"
          >
            {{ copied ? t('Copied') : t('Copy') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="authProvider !== 'none'" class="w-full h-[1px] bg-[var(--border-main)]" />

    <div v-if="authProvider !== 'none'" class="rounded-[12px] p-[12px] -m-[12px]">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex flex-col items-start justify-center flex-1 min-w-0">
          <span class="text-sm font-medium text-[var(--text-primary)]">{{ t('Logout') }}</span>
          <div class="text-[13px] text-[var(--text-tertiary)] leading-[18px] w-full">
            {{ t('Sign out of your account on this device.') }}
          </div>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 outline outline-1 -outline-offset-1 hover:bg-[var(--fill-tsp-white-light)] text-[var(--function-error)] outline-[var(--border-btn-main)] bg-transparent h-[32px]"
          @click="handleLogout"
        >
          {{ t('Logout') }}
        </button>
      </div>
    </div>

    <div v-if="authProvider !== 'none'" class="rounded-[12px] p-[12px] -m-[12px]">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex flex-col items-start justify-center flex-1 min-w-0">
          <span class="text-sm font-medium text-[var(--text-primary)]">{{ t('Log out of all devices') }}</span>
          <div class="text-[13px] text-[var(--text-tertiary)] leading-[18px] w-full">
            {{ t('Sign out of your account everywhere, including other browsers and devices.') }}
          </div>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 outline outline-1 -outline-offset-1 hover:bg-[var(--fill-tsp-white-light)] text-[var(--function-error)] outline-[var(--border-btn-main)] bg-transparent h-[32px]"
          @click="handleLogoutAll"
        >
          {{ t('Log out everywhere') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '@/composables/useAuth'
import { useDialog } from '@/composables/useDialog'
import UserAvatar from '@/components/UserAvatar.vue'
import AvatarCropDialog from './AvatarCropDialog.vue'
import { changeFullname, uploadAvatar, removeAvatar } from '@/api/auth'
import { getCachedAuthProvider } from '@/api/config'
import { showSuccessToast, showErrorToast } from '@/utils/toast'

const router = useRouter()
const { t } = useI18n()
const { currentUser, logout, logoutAll, loadCurrentUser } = useAuth()
const { showConfirmDialog } = useDialog()
const authProvider = ref<string | null>(null)
const localFullname = ref(currentUser.value?.fullname || '')
const copied = ref(false)

const fileInputRef = ref<HTMLInputElement | null>(null)
const pickedFile = ref<File | null>(null)

const MAX_AVATAR_BYTES = 5 * 1024 * 1024
const ALLOWED_AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp']

const avatarLetter = computed(() =>
  currentUser.value?.fullname?.charAt(0)?.toUpperCase() || 'M',
)

watch(currentUser, (user) => {
  if (user) localFullname.value = user.fullname || ''
}, { immediate: true })

const updateFullname = async (newFullname: string) => {
  if (!newFullname.trim() || newFullname === currentUser.value?.fullname) return
  try {
    await changeFullname({ fullname: newFullname.trim() })
    await loadCurrentUser()
    showSuccessToast(t('Full name updated successfully'))
  } catch (error: unknown) {
    localFullname.value = currentUser.value?.fullname || ''
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    showErrorToast(err?.response?.data?.message || err?.message || t('Failed to update full name'))
  }
}

const handleFullnameSubmit = () => {
  updateFullname(localFullname.value)
}

const triggerFilePicker = () => {
  fileInputRef.value?.click()
}

const onFilePicked = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // allow picking the same file again later
  if (!file) return
  if (!ALLOWED_AVATAR_TYPES.includes(file.type)) {
    showErrorToast(t('Please choose a JPEG, PNG, or WebP image.'))
    return
  }
  if (file.size > MAX_AVATAR_BYTES) {
    showErrorToast(t('Image must be 5MB or smaller.'))
    return
  }
  pickedFile.value = file
}

const handleCropSaved = async (blob: Blob) => {
  pickedFile.value = null
  try {
    await uploadAvatar(blob)
    await loadCurrentUser()
    showSuccessToast(t('Profile photo updated'))
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    showErrorToast(err?.response?.data?.message || err?.message || t('Failed to update profile photo'))
  }
}

const handleRemoveAvatar = async () => {
  try {
    await removeAvatar()
    await loadCurrentUser()
    showSuccessToast(t('Profile photo removed'))
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    showErrorToast(err?.response?.data?.message || err?.message || t('Failed to remove profile photo'))
  }
}

const copyUserId = async () => {
  const id = currentUser.value?.id
  if (!id) return
  try {
    await navigator.clipboard.writeText(id)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    showErrorToast(t('Failed to copy'))
  }
}

const handleLogout = async () => {
  try {
    await logout()
    router.push('/login')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}

const handleLogoutAll = () => {
  showConfirmDialog({
    title: t('Log out of all devices'),
    content: t('This will sign you out everywhere, including other browsers and devices. You will need to log in again.'),
    confirmText: t('Log out everywhere'),
    confirmType: 'danger',
    onConfirm: async () => {
      try {
        await logoutAll()
        router.push('/login')
      } catch (error) {
        console.error('Logout-all failed:', error)
      }
    }
  })
}

onMounted(async () => {
  authProvider.value = await getCachedAuthProvider()
})
</script>
