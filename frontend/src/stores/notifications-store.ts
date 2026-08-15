import { create } from 'zustand'

export type NotificationsConnectionStatus =
  'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

interface NotificationsState {
  /** Unread count for the badge (TSC-NOTIF-002), independent of whichever
   * page of the notifications list happens to be cached — kept in its own
   * store rather than derived from `useInfiniteQuery` pages so it stays
   * correct even before the panel has ever been opened/fetched. */
  unreadCount: number
  /** Live WebSocket connection state, surfaced so the panel can show a
   * "reconnecting…" affordance instead of silently going stale. */
  connectionStatus: NotificationsConnectionStatus
  setUnreadCount: (count: number) => void
  increment: () => void
  setConnectionStatus: (status: NotificationsConnectionStatus) => void
  /** Logout (TSC-NOTIF-002 acceptance criterion: "logout ... clears
   * user-specific notification state"). */
  reset: () => void
}

export const useNotificationsStore = create<NotificationsState>((set) => ({
  unreadCount: 0,
  connectionStatus: 'idle',
  setUnreadCount: (count) => set({ unreadCount: Math.max(0, count) }),
  increment: () => set((state) => ({ unreadCount: state.unreadCount + 1 })),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  reset: () => set({ unreadCount: 0, connectionStatus: 'idle' }),
}))
