import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'

export interface TabItem {
  id: string
  label: string
  content: ReactNode
  disabled?: boolean
}

export interface TabsProps {
  tabs: TabItem[]
  /** Accessible name for the tab list. */
  'aria-label': string
  defaultTab?: string
}

/**
 * WAI-ARIA tabs with roving tabindex.
 *
 * Keyboard: Left/Right (and Home/End) move between tabs; the focused tab is
 * selected automatically (automatic activation). Only the active tab is in
 * the tab order; panels are associated via aria-controls / aria-labelledby.
 */
export function Tabs({ tabs, defaultTab, 'aria-label': ariaLabel }: TabsProps) {
  const baseId = useId()
  const enabledTabs = tabs.filter((t) => !t.disabled)
  const [activeId, setActiveId] = useState(
    defaultTab ?? enabledTabs[0]?.id ?? tabs[0]?.id,
  )
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())

  const setTabRef = useCallback(
    (id: string) => (node: HTMLButtonElement | null) => {
      if (node) tabRefs.current.set(id, node)
      else tabRefs.current.delete(id)
    },
    [],
  )

  function focusTab(id: string) {
    setActiveId(id)
    tabRefs.current.get(id)?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const currentIndex = enabledTabs.findIndex((t) => t.id === activeId)
    if (currentIndex === -1) return

    let nextIndex: number | null = null
    switch (event.key) {
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % enabledTabs.length
        break
      case 'ArrowLeft':
        nextIndex =
          (currentIndex - 1 + enabledTabs.length) % enabledTabs.length
        break
      case 'Home':
        nextIndex = 0
        break
      case 'End':
        nextIndex = enabledTabs.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    focusTab(enabledTabs[nextIndex].id)
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label={ariaLabel}
        onKeyDown={onKeyDown}
        className="flex border-b border-border"
      >
        {tabs.map((tab) => {
          const selected = tab.id === activeId
          return (
            <button
              key={tab.id}
              ref={setTabRef(tab.id)}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              disabled={tab.disabled}
              onClick={() => setActiveId(tab.id)}
              className={[
                'cursor-pointer px-4 py-2 text-sm font-semibold transition-colors duration-150 motion-reduce:transition-none',
                'disabled:cursor-not-allowed disabled:opacity-50',
                selected
                  ? 'border-b-2 border-brand text-foreground'
                  : 'text-muted hover:bg-surface-hover hover:text-foreground',
              ].join(' ')}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${baseId}-panel-${tab.id}`}
          aria-labelledby={`${baseId}-tab-${tab.id}`}
          hidden={tab.id !== activeId}
          tabIndex={0}
          className="py-4"
        >
          {tab.content}
        </div>
      ))}
    </div>
  )
}
