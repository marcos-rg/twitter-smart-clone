import { useCallback, useEffect, useRef } from 'react'

export interface UseInfiniteScrollTriggerOptions {
  /** Whether a next page exists to load. */
  hasNextPage: boolean
  /** Whether a page fetch is already in flight — guards against issuing a
   * second request for the same trigger while one is pending. */
  isFetchingNextPage: boolean
  /** Called (at most once per intersection) when the sentinel scrolls into
   * view and a load is not already in flight. */
  onLoadMore: () => void
  /** Root margin passed to the underlying `IntersectionObserver`, so the
   * next page starts loading slightly before the sentinel is actually on
   * screen. Defaults to `'200px'`. */
  rootMargin?: string
}

/**
 * Drives infinite-scroll pagination off an `IntersectionObserver` watching
 * a sentinel element, rather than a scroll-event listener (TSC-FEED-002).
 *
 * Returns a callback ref to attach to the sentinel node. The observer is
 * created when the node mounts and disconnected when it unmounts *or* the
 * component using this hook unmounts — the acceptance criterion "observer
 * cleanup prevents requests after unmount" holds because `IntersectionObserver.disconnect()`
 * is always called before the node (and this hook) goes away, so no queued
 * callback can fire afterward.
 *
 * The "each next cursor is requested at most once per trigger" acceptance
 * criterion holds because `onLoadMore` only runs when the sentinel's
 * intersection *changes* to intersecting (a native `IntersectionObserver`
 * property — the callback fires on threshold crossings, not continuously)
 * and only when `isFetchingNextPage` is currently `false`; the latest values
 * are read from a ref inside the observer callback so a stale closure can
 * never re-trigger a load that's already in flight.
 */
export function useInfiniteScrollTrigger({
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
  rootMargin = '200px',
}: UseInfiniteScrollTriggerOptions) {
  const stateRef = useRef({ hasNextPage, isFetchingNextPage, onLoadMore })
  stateRef.current = { hasNextPage, isFetchingNextPage, onLoadMore }

  const observerRef = useRef<IntersectionObserver | null>(null)

  const sentinelRef = useCallback(
    (node: HTMLElement | null) => {
      observerRef.current?.disconnect()
      observerRef.current = null
      if (!node) return

      const observer = new IntersectionObserver(
        (entries) => {
          const entry = entries[0]
          const current = stateRef.current
          if (entry?.isIntersecting && current.hasNextPage && !current.isFetchingNextPage) {
            current.onLoadMore()
          }
        },
        { rootMargin },
      )
      observer.observe(node)
      observerRef.current = observer
    },
    [rootMargin],
  )

  useEffect(() => {
    return () => {
      observerRef.current?.disconnect()
      observerRef.current = null
    }
  }, [])

  return sentinelRef
}
