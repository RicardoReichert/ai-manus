import { describe, it, expect, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { useDialog } from '../useDialog'
import { i18n } from '../useI18n'

function withSetup<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setup()
        return () => null
      }
    }),
    { global: { plugins: [i18n] } }
  )
  return { result, wrapper }
}

describe('useDialog', () => {
  it('showConfirmDialog sets visible, title/content, inputEnabled false, default texts', () => {
    const { result: dialog } = withSetup(() => useDialog())

    dialog.showConfirmDialog({
      title: 'My Title',
      content: 'My Content',
      onConfirm: vi.fn()
    })

    expect(dialog.dialogVisible.value).toBe(true)
    expect(dialog.dialogConfig.title).toBe('My Title')
    expect(dialog.dialogConfig.content).toBe('My Content')
    expect(dialog.dialogConfig.inputEnabled).toBe(false)
    expect(dialog.dialogConfig.confirmText).toBe('Confirm')
    expect(dialog.dialogConfig.cancelText).toBe('Cancel')
  })

  it('showConfirmDialog confirmType defaults to primary, honors danger', () => {
    const { result: dialog } = withSetup(() => useDialog())

    dialog.showConfirmDialog({ title: 't', content: 'c' })
    expect(dialog.dialogConfig.confirmType).toBe('primary')

    dialog.showConfirmDialog({ title: 't', content: 'c', confirmType: 'danger' })
    expect(dialog.dialogConfig.confirmType).toBe('danger')
  })

  it('handleConfirm calls onConfirm (awaiting a promise) then closes the dialog', async () => {
    const { result: dialog } = withSetup(() => useDialog())
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    dialog.showConfirmDialog({ title: 't', content: 'c', onConfirm })

    await dialog.handleConfirm()

    expect(onConfirm).toHaveBeenCalled()
    expect(dialog.dialogVisible.value).toBe(false)
  })

  it('handleCancel calls onCancel then closes; no onCancel does not throw', () => {
    const { result: dialog } = withSetup(() => useDialog())
    const onCancel = vi.fn()
    dialog.showConfirmDialog({ title: 't', content: 'c', onCancel })

    dialog.handleCancel()

    expect(onCancel).toHaveBeenCalled()
    expect(dialog.dialogVisible.value).toBe(false)

    dialog.showConfirmDialog({ title: 't', content: 'c' })
    expect(() => dialog.handleCancel()).not.toThrow()
    expect(dialog.dialogVisible.value).toBe(false)
  })

  it('showInputDialog sets inputEnabled true and inputValue from initialValue (or empty)', () => {
    const { result: dialog } = withSetup(() => useDialog())

    dialog.showInputDialog({ title: 't', initialValue: 'hello', onConfirm: vi.fn() })
    expect(dialog.dialogConfig.inputEnabled).toBe(true)
    expect(dialog.dialogConfig.inputValue).toBe('hello')

    dialog.showInputDialog({ title: 't', onConfirm: vi.fn() })
    expect(dialog.dialogConfig.inputEnabled).toBe(true)
    expect(dialog.dialogConfig.inputValue).toBe('')
  })

  it('handleConfirm after showInputDialog calls onConfirm with trimmed inputValue', async () => {
    const { result: dialog } = withSetup(() => useDialog())
    const onConfirm = vi.fn()
    dialog.showInputDialog({ title: 't', onConfirm })

    dialog.dialogConfig.inputValue = '  x  '
    await dialog.handleConfirm()

    expect(onConfirm).toHaveBeenCalledWith('x')
    expect(dialog.dialogVisible.value).toBe(false)
  })

  it('showDeleteSessionDialog is a danger confirm dialog with real translated copy', async () => {
    const { result: dialog } = withSetup(() => useDialog())
    const onConfirm = vi.fn()

    dialog.showDeleteSessionDialog(onConfirm)

    expect(dialog.dialogVisible.value).toBe(true)
    expect(dialog.dialogConfig.confirmType).toBe('danger')
    expect(dialog.dialogConfig.inputEnabled).toBe(false)
    expect(dialog.dialogConfig.title).toBe('Are you sure you want to delete this session?')
    expect(dialog.dialogConfig.content).toBe(
      'The chat history of this session cannot be recovered after deletion.'
    )
    expect(dialog.dialogConfig.confirmText).toBe('Delete')
    expect(dialog.dialogConfig.cancelText).toBe('Cancel')

    await dialog.handleConfirm()

    expect(onConfirm).toHaveBeenCalled()
    expect(dialog.dialogVisible.value).toBe(false)
  })
})
