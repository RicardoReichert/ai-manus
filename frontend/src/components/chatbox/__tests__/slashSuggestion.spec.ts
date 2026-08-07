import { describe, it, expect, vi } from 'vitest'
import { buildSlashItems, applySlashSelection, type SlashItem } from '../slashSuggestion'

describe('slashSuggestion', () => {
  describe('buildSlashItems', () => {
    it('returns an array with exactly one item', () => {
      const fn = vi.fn()
      const result = buildSlashItems(fn)
      expect(result).toHaveLength(1)
    })

    it('returns an item with id "add_local_files"', () => {
      const fn = vi.fn()
      const result = buildSlashItems(fn)
      expect(result[0].id).toBe('add_local_files')
    })

    it('returns an item with titleKey "Add local files"', () => {
      const fn = vi.fn()
      const result = buildSlashItems(fn)
      expect(result[0].titleKey).toBe('Add local files')
    })

    it('returns an item where run is the passed function by reference', () => {
      const fn = vi.fn()
      const result = buildSlashItems(fn)
      expect(result[0].run).toBe(fn)
    })
  })

  describe('applySlashSelection', () => {
    it('calls command(item) exactly once when command is provided', () => {
      const command = vi.fn()
      const item: SlashItem = {
        id: 'add_local_files',
        titleKey: 'Add local files',
        run: vi.fn(),
      }
      applySlashSelection({
        editor: null,
        range: null,
        command,
        item,
      })
      expect(command).toHaveBeenCalledTimes(1)
      expect(command).toHaveBeenCalledWith(item)
    })

    it('does not call item.run() when command is provided', () => {
      const command = vi.fn()
      const itemRun = vi.fn()
      const item: SlashItem = {
        id: 'add_local_files',
        titleKey: 'Add local files',
        run: itemRun,
      }
      applySlashSelection({
        editor: null,
        range: null,
        command,
        item,
      })
      expect(itemRun).not.toHaveBeenCalled()
    })

    it('does not touch editor when command is provided', () => {
      const command = vi.fn()
      const editor = {
        chain: vi.fn(),
      }
      const item: SlashItem = {
        id: 'add_local_files',
        titleKey: 'Add local files',
        run: vi.fn(),
      }
      applySlashSelection({
        editor: editor as any,
        range: { from: 0, to: 5 },
        command,
        item,
      })
      expect(editor.chain).not.toHaveBeenCalled()
    })

    it('invokes editor chain and calls item.run() when command is null but editor and range are provided', () => {
      const itemRun = vi.fn()
      const deleteRangeRun = vi.fn()
      const editor = {
        chain: vi.fn(() => ({
          focus: vi.fn(function () {
            return {
              deleteRange: vi.fn(function () {
                return { run: deleteRangeRun }
              }),
            }
          }),
        })),
      }
      const item: SlashItem = {
        id: 'add_local_files',
        titleKey: 'Add local files',
        run: itemRun,
      }
      const range = { from: 0, to: 5 }
      applySlashSelection({
        editor: editor as any,
        range,
        command: null,
        item,
      })
      expect(editor.chain).toHaveBeenCalled()
      expect(deleteRangeRun).toHaveBeenCalled()
      expect(itemRun).toHaveBeenCalled()
    })

    it('only calls item.run() when command, editor, and range are all null/undefined', () => {
      const itemRun = vi.fn()
      const item: SlashItem = {
        id: 'add_local_files',
        titleKey: 'Add local files',
        run: itemRun,
      }
      applySlashSelection({
        editor: null,
        range: null,
        command: null,
        item,
      })
      expect(itemRun).toHaveBeenCalledTimes(1)
    })

    it('does not throw when command, editor, and range are all null/undefined', () => {
      const itemRun = vi.fn()
      const item: SlashItem = {
        id: 'add_local_files',
        titleKey: 'Add local files',
        run: itemRun,
      }
      expect(() => {
        applySlashSelection({
          editor: null,
          range: null,
          command: null,
          item,
        })
      }).not.toThrow()
    })
  })
})
