import { useState } from 'react'
import { Button, EmptyState, ErrorState, Input } from '../components/ui'
import { SearchModeSelector } from '../features/users/SearchModeSelector'
import { UserCard, UserCardSkeleton } from '../features/users/UserCard'
import { describeUsersError, useUserSearch } from '../features/users/hooks'
import { useDebouncedValue } from '../lib/useDebouncedValue'
import type { SearchMode } from '../api/types'

const SEARCH_DEBOUNCE_MS = 300

/**
 * User search screen: query input, exact/prefix/fuzzy mode selection, and
 * cursor-paginated results. The query is debounced before it drives the
 * network request; mode changes apply immediately (no debounce) since they
 * aren't typed input.
 */
export function Search() {
  const [rawQuery, setRawQuery] = useState('')
  const [mode, setMode] = useState<SearchMode>('prefix')
  const debouncedQuery = useDebouncedValue(rawQuery, SEARCH_DEBOUNCE_MS)

  const search = useUserSearch(debouncedQuery, mode)
  const hasTypedQuery = rawQuery.trim().length > 0
  const items = search.data?.pages.flatMap((page) => page.data) ?? []
  // True while the debounce timer is pending for the latest keystroke, or
  // while the resulting request is in flight — keeps the loading indicator
  // accurate instead of flashing "no results" between typing and fetching.
  const isPendingSearch = rawQuery !== debouncedQuery

  return (
    <div className="flex flex-col gap-4 p-4">
      <header>
        <h1>Search</h1>
      </header>
      <Input
        label="Search people"
        placeholder="Search by name or username"
        value={rawQuery}
        onChange={(event) => setRawQuery(event.target.value)}
        autoComplete="off"
      />
      <SearchModeSelector value={mode} onChange={setMode} />

      <div>
        {!hasTypedQuery ? (
          <EmptyState
            title="Search for people"
            description="Type a name or username to find someone."
          />
        ) : isPendingSearch || search.isLoading ? (
          <>
            <UserCardSkeleton />
            <UserCardSkeleton />
            <UserCardSkeleton />
          </>
        ) : search.isError ? (
          <ErrorState
            title="Search failed"
            description={describeUsersError(search.error)}
            onRetry={() => void search.refetch()}
          />
        ) : items.length === 0 ? (
          <EmptyState
            title="No users found"
            description={`No results for "${debouncedQuery}" in ${mode} mode.`}
          />
        ) : (
          <>
            {items.map((user) => (
              <UserCard key={user.id} name={user.name} username={user.username} bio={user.bio} />
            ))}
            {search.hasNextPage ? (
              <div className="flex justify-center p-4">
                <Button
                  variant="outline"
                  loading={search.isFetchingNextPage}
                  onClick={() => void search.fetchNextPage()}
                >
                  Load more
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
