import { useCallback, useRef, type KeyboardEvent } from 'react'
import type { SearchMode } from '../../api/types'

export interface SearchModeSelectorProps {
  value: SearchMode
  onChange: (mode: SearchMode) => void
}

const MODES: { id: SearchMode; label: string }[] = [
  { id: 'prefix', label: 'Prefix' },
  { id: 'exact', label: 'Exact' },
  { id: 'fuzzy', label: 'Fuzzy' },
]

/**
 * Single-select mode control (WAI-ARIA `radiogroup` pattern, not `tablist` —
 * there is one results list whose filter changes, not separate panels, so
 * `Tabs` — which mounts every panel simultaneously — would fire all three
 * searches at once). Roving tabindex with Left/Right/Home/End, matching the
 * keyboard behavior of `Tabs`.
 */
export function SearchModeSelector({ value, onChange }: SearchModeSelectorProps) {
  const buttonRefs = useRef(new Map<SearchMode, HTMLButtonElement>())

  const setButtonRef = useCallback(
    (id: SearchMode) => (node: HTMLButtonElement | null) => {
      if (node) buttonRefs.current.set(id, node)
      else buttonRefs.current.delete(id)
    },
    [],
  )

  function select(mode: SearchMode, focus: boolean) {
    onChange(mode)
    if (focus) buttonRefs.current.get(mode)?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const currentIndex = MODES.findIndex((mode) => mode.id === value)
    if (currentIndex === -1) return

    let nextIndex: number | null = null
    switch (event.key) {
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % MODES.length
        break
      case 'ArrowLeft':
        nextIndex = (currentIndex - 1 + MODES.length) % MODES.length
        break
      case 'Home':
        nextIndex = 0
        break
      case 'End':
        nextIndex = MODES.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    select(MODES[nextIndex].id, true)
  }

  return (
    <div role="radiogroup" aria-label="Search mode" onKeyDown={onKeyDown} className="flex gap-2">
      {MODES.map((mode) => {
        const selected = mode.id === value
        return (
          <button
            key={mode.id}
            ref={setButtonRef(mode.id)}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => select(mode.id, false)}
            className={[
              'cursor-pointer rounded-full px-4 py-1.5 text-sm font-semibold transition-colors duration-150 motion-reduce:transition-none',
              selected
                ? 'bg-brand text-white'
                : 'border border-border text-foreground hover:bg-surface-hover',
            ].join(' ')}
          >
            {mode.label}
          </button>
        )
      })}
    </div>
  )
}
