import { useEffect, useState } from 'react'

/** Tracks `navigator.onLine`, updated live via the `online`/`offline`
 * window events. Used to show an offline banner on data-heavy screens like
 * the home feed (TSC-FEED-002) instead of a generic error when a fetch
 * fails purely because the device has no connection. */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  )

  useEffect(() => {
    function handleOnline() {
      setIsOnline(true)
    }
    function handleOffline() {
      setIsOnline(false)
    }
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return isOnline
}
