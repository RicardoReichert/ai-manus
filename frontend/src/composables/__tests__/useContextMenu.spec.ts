import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useContextMenu, createMenuItem, createDangerMenuItem, createSubmenuItem, createSeparator } from '../useContextMenu'

describe('useContextMenu', () => {
  beforeEach(() => {
    const { hideContextMenu } = useContextMenu()
    hideContextMenu()
  })

  describe('showContextMenu', () => {
    it('sets contextMenuVisible, selectedItemId, targetElement, and menuItems', () => {
      const { showContextMenu, contextMenuVisible, selectedItemId, targetElement, menuItems } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]

      showContextMenu('item-1', element, items)

      expect(contextMenuVisible.value).toBe(true)
      expect(selectedItemId.value).toBe('item-1')
      expect(targetElement.value).toBe(element)
      expect(menuItems.value).toStrictEqual(items)
    })

    it('registers the onClick handler', () => {
      const { showContextMenu, handleMenuItemClick } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]
      const onClick = vi.fn()

      showContextMenu('item-1', element, items, onClick)
      handleMenuItemClick(items[0])

      expect(onClick).toHaveBeenCalledWith('test', 'item-1')
    })

    it('registers the onClose handler', () => {
      const { showContextMenu, hideContextMenu } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]
      const onClose = vi.fn()

      showContextMenu('item-1', element, items, undefined, onClose)
      hideContextMenu()

      expect(onClose).toHaveBeenCalledWith('item-1')
    })

    it('implicitly calls hideContextMenu first when already visible', () => {
      const { showContextMenu, hideContextMenu } = useContextMenu()
      const element1 = document.createElement('div')
      const element2 = document.createElement('div')
      const items1 = [createMenuItem('test1', 'Test Item 1')]
      const items2 = [createMenuItem('test2', 'Test Item 2')]
      const onClose1 = vi.fn()
      const onClose2 = vi.fn()

      // Show first menu
      showContextMenu('item-1', element1, items1, undefined, onClose1)
      // Show second menu (should call first menu's onClose)
      showContextMenu('item-2', element2, items2, undefined, onClose2)

      expect(onClose1).toHaveBeenCalledWith('item-1')
      expect(onClose2).not.toHaveBeenCalled()

      // Now hide second menu
      hideContextMenu()
      expect(onClose2).toHaveBeenCalledWith('item-2')
    })
  })

  describe('hideContextMenu', () => {
    it('resets all fields to defaults', () => {
      const { showContextMenu, hideContextMenu, contextMenuVisible, selectedItemId, menuItems, targetElement } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]

      showContextMenu('item-1', element, items)
      hideContextMenu()

      expect(contextMenuVisible.value).toBe(false)
      expect(selectedItemId.value).toBeUndefined()
      expect(menuItems.value).toEqual([])
      expect(targetElement.value).toBeNull()
    })

    it('calls onClose callback if registered', () => {
      const { showContextMenu, hideContextMenu } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]
      const onClose = vi.fn()

      showContextMenu('item-1', element, items, undefined, onClose)
      hideContextMenu()

      expect(onClose).toHaveBeenCalledWith('item-1')
    })

    it('does not call onClose if no onClose was registered', () => {
      const { showContextMenu, hideContextMenu } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]
      const onClose = vi.fn()

      showContextMenu('item-1', element, items)
      hideContextMenu()

      expect(onClose).not.toHaveBeenCalled()
    })

    it('does not call onClose if no selectedItemId', () => {
      const { hideContextMenu } = useContextMenu()
      const onClose = vi.fn()

      // Call hideContextMenu directly without showContextMenu first
      hideContextMenu()

      expect(onClose).not.toHaveBeenCalled()
    })
  })

  describe('handleMenuItemClick', () => {
    it('calls onClick handler and item.action then hides menu for normal item', () => {
      const { showContextMenu, handleMenuItemClick, contextMenuVisible } = useContextMenu()
      const element = document.createElement('div')
      const itemAction = vi.fn()
      const items = [createMenuItem('test', 'Test Item', { action: itemAction })]
      const onClick = vi.fn()

      showContextMenu('item-1', element, items, onClick)
      handleMenuItemClick(items[0])

      expect(onClick).toHaveBeenCalledWith('test', 'item-1')
      expect(itemAction).toHaveBeenCalledWith('item-1')
      expect(contextMenuVisible.value).toBe(false)
    })

    it('does nothing for disabled item', () => {
      const { showContextMenu, handleMenuItemClick, contextMenuVisible } = useContextMenu()
      const element = document.createElement('div')
      const itemAction = vi.fn()
      const items = [createMenuItem('test', 'Test Item', { disabled: true, action: itemAction })]
      const onClick = vi.fn()

      showContextMenu('item-1', element, items, onClick)
      handleMenuItemClick(items[0])

      expect(onClick).not.toHaveBeenCalled()
      expect(itemAction).not.toHaveBeenCalled()
      expect(contextMenuVisible.value).toBe(true)
    })

    it('does nothing for submenu parent item with children', () => {
      const { showContextMenu, handleMenuItemClick, contextMenuVisible } = useContextMenu()
      const element = document.createElement('div')
      const child = createMenuItem('child', 'Child Item')
      const items = [createSubmenuItem('parent', 'Parent Item', [child])]
      const onClick = vi.fn()

      showContextMenu('item-1', element, items, onClick)
      handleMenuItemClick(items[0])

      expect(onClick).not.toHaveBeenCalled()
      expect(contextMenuVisible.value).toBe(true)
    })

    it('calls only onClick handler if item.action is not provided', () => {
      const { showContextMenu, handleMenuItemClick } = useContextMenu()
      const element = document.createElement('div')
      const items = [createMenuItem('test', 'Test Item')]
      const onClick = vi.fn()

      showContextMenu('item-1', element, items, onClick)
      handleMenuItemClick(items[0])

      expect(onClick).toHaveBeenCalledWith('test', 'item-1')
    })
  })

  describe('createMenuItem', () => {
    it('creates a menu item with default variant', () => {
      const item = createMenuItem('key-1', 'Label 1')

      expect(item.key).toBe('key-1')
      expect(item.label).toBe('Label 1')
      expect(item.variant).toBe('default')
      expect(item.icon).toBeUndefined()
      expect(item.children).toBeUndefined()
    })

    it('creates a menu item with custom options', () => {
      const customIcon = { name: 'icon' }
      const item = createMenuItem('key-1', 'Label 1', { icon: customIcon, checked: true })

      expect(item.key).toBe('key-1')
      expect(item.label).toBe('Label 1')
      expect(item.variant).toBe('default')
      expect(item.icon).toBeDefined()
      expect(item.checked).toBe(true)
    })
  })

  describe('createDangerMenuItem', () => {
    it('creates a menu item with danger variant', () => {
      const item = createDangerMenuItem('key-1', 'Delete')

      expect(item.key).toBe('key-1')
      expect(item.label).toBe('Delete')
      expect(item.variant).toBe('danger')
    })

    it('accepts custom options', () => {
      const item = createDangerMenuItem('key-1', 'Delete', { disabled: true })

      expect(item.key).toBe('key-1')
      expect(item.label).toBe('Delete')
      expect(item.variant).toBe('danger')
      expect(item.disabled).toBe(true)
    })
  })

  describe('createSubmenuItem', () => {
    it('creates a submenu item with default variant and children', () => {
      const child = createMenuItem('child-1', 'Child')
      const item = createSubmenuItem('parent', 'Parent', [child])

      expect(item.key).toBe('parent')
      expect(item.label).toBe('Parent')
      expect(item.variant).toBe('default')
      expect(item.children).toEqual([child])
    })

    it('accepts custom options', () => {
      const child = createMenuItem('child-1', 'Child')
      const item = createSubmenuItem('parent', 'Parent', [child], { checked: true })

      expect(item.key).toBe('parent')
      expect(item.label).toBe('Parent')
      expect(item.variant).toBe('default')
      expect(item.children).toEqual([child])
      expect(item.checked).toBe(true)
    })
  })

  describe('createSeparator', () => {
    it('creates a separator with empty label and disabled flag', () => {
      const item = createSeparator()

      expect(item.label).toBe('')
      expect(item.disabled).toBe(true)
      expect(item.key).toMatch(/^separator-/)
    })

    it('generates unique keys for each separator', () => {
      const item1 = createSeparator()
      const item2 = createSeparator()

      expect(item1.key).not.toBe(item2.key)
      expect(item1.key).toMatch(/^separator-/)
      expect(item2.key).toMatch(/^separator-/)
    })
  })
})
