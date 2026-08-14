import { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { ProfileEditForm } from '../features/users/ProfileEditForm'
import { useToast } from '../components/ui'
import { useAuthStore } from '../stores/auth-store'

/**
 * Edit screen for the signed-in user's own profile. Initial field values come
 * straight from the in-memory auth store's `user` (already the full private
 * shape, including email, from login/session restore) rather than an extra
 * `GET /users/{username}` round trip — that endpoint never returns email
 * anyway (see `ProfileHeader`'s doc comment).
 *
 * Only the profile owner may land here: visiting `/profile/:username/edit`
 * for anyone else redirects to the read-only profile view instead of
 * rendering a form that would silently edit the wrong account.
 */
export function ProfileEdit() {
  const { username } = useParams<{ username: string }>()
  const navigate = useNavigate()
  const { toast } = useToast()
  const currentUser = useAuthStore((state) => state.user)

  // Captured once at mount, not re-derived on every render: a successful
  // save changes `currentUser.username` (via this screen's own mutation)
  // before the resulting `navigate()` away from here lands. Re-checking
  // against the *live* store value on that in-between render would see the
  // still-old `:username` route param next to the already-new store
  // username, look like "editing someone else's profile", and redirect to
  // the stale old-username profile instead of letting the real navigation
  // (below, in `onSuccess`) win.
  const [isAuthorized] = useState(() =>
    Boolean(
      username && currentUser && username.toLowerCase() === currentUser.username.toLowerCase(),
    ),
  )

  if (!currentUser || !isAuthorized) {
    return <Navigate to={`/profile/${username ?? ''}`} replace />
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-10">
      <header>
        <h1>Edit profile</h1>
      </header>
      <ProfileEditForm
        initialValues={{
          name: currentUser.name,
          username: currentUser.username,
          email: currentUser.email,
          bio: currentUser.bio ?? '',
        }}
        onSuccess={(newUsername) => {
          toast('Profile updated.', 'success')
          navigate(`/profile/${newUsername}`, { replace: true })
        }}
        onCancel={() => navigate(`/profile/${currentUser.username}`)}
      />
    </div>
  )
}
