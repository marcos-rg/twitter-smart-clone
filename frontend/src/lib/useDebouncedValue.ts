import { useEffect, useState } from 'react'

/** Returns `value`, but only after it has stopped changing for `delayMs`.
 * Used to avoid firing a network request on every keystroke (e.g. user
 * search). The debounced value only updates via a `setTimeout` scheduled in
 * an effect keyed on `value`/`delayMs`, so a rapid sequence of updates
 * cancels every prior pending timeout and only the final value ever lands. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
