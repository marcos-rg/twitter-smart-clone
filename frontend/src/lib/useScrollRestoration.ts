import { useEffect, useLayoutEffect, useRef } from 'react'
import { useNavigationType } from 'react-router-dom'

/**
 * Approved scroll-restoration policy for the home feed (TSC-FEED-002 human
 * review gate). `App.tsx` uses a plain declarative `<BrowserRouter>`, not a
 * data router, so React Router's own `<ScrollRestoration>` (data-router
 * only) isn't available — this hook is the equivalent for a single screen.
 *
 * Policy:
 * - **Back/forward navigation** (browser back button, or `navigate(-1)`
 *   from a tweet's detail page) restores the exact scroll offset the feed
 *   was at when the user left it — the common "go look at a tweet, come
 *   back where you were" flow shouldn't lose your place.
 * - **Any other arrival at the feed** (a fresh load, or clicking a nav
 *   link/logo back to "/") starts at the top, same as any other page —
 *   restoring a stale scroll position when the user is *choosing* to
 *   revisit the feed (rather than backing out of a detail view) would be
 *   surprising, not helpful.
 *
 * The saved position is keyed in `sessionStorage` (survives a reload,
 * cleared at tab close) so it also works across a hard navigation, and is
 * scoped to `key`, one entry per screen using this hook.
 */
export function useScrollRestoration(key: string, { ready }: { ready: boolean }) {
  const navigationType = useNavigationType()
  const storageKey = `scroll-restoration:${key}`
  const restoredRef = useRef(false)

  // Restore once the content this screen needs is actually rendered
  // (`ready`) — restoring against an empty/loading page would scroll to a
  // position that doesn't exist yet.
  useLayoutEffect(() => {
    if (restoredRef.current || !ready) return
    restoredRef.current = true

    if (navigationType !== 'POP') {
      // Explicit, not just "leave it wherever it happened to be": a fresh
      // arrival always starts at the top, even if a stale position is
      // still sitting in `sessionStorage` from an earlier visit.
      window.scrollTo(0, 0)
      return
    }

    const saved = window.sessionStorage.getItem(storageKey)
    if (saved === null) return
    const y = Number(saved)
    if (Number.isFinite(y)) window.scrollTo(0, y)
    // navigationType/storageKey are stable for the lifetime of a mounted
    // screen; only `ready` flipping to true should re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready])

  // Save the current scroll position continuously (not just on unmount) so
  // a save always lands even if the tab closes or the component unmounts
  // without a chance to run cleanup synchronously.
  useEffect(() => {
    function save() {
      window.sessionStorage.setItem(storageKey, String(window.scrollY))
    }
    window.addEventListener('scroll', save, { passive: true })
    return () => {
      save()
      window.removeEventListener('scroll', save)
    }
  }, [storageKey])
}
