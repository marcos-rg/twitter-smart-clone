import { EmptyState } from '../components/ui'

/**
 * Placeholder home route. Feature pages (feed, profile, etc.) replace this in
 * later tasks; for now it proves the AppShell + routing work end to end.
 */
export function Home() {
  return (
    <div>
      <header className="border-b border-border px-4 py-4">
        <h1>Twitter Smart Clone</h1>
      </header>
      <div className="p-4">
        <EmptyState
          title="Frontend scaffold ready"
          description="The feed is implemented in a later task. Visit the Design Lab to browse the component library."
        />
      </div>
    </div>
  )
}
