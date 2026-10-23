import { useMemo, useState, type FormEvent } from 'react'
import type { AdminUser } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { ErrorNotice, Loading } from '../../components/common'
import { useAdminUsers, useResetPassword } from '../../hooks/useAdmin'
import { generatePassword } from '../../lib/password'

const MIN_LENGTH = 8

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—')

/** Inline form under a user's row: type or generate a new password, copy it, save. */
function ResetForm({ user, isSelf, onDone }: { user: AdminUser; isSelf: boolean; onDone: (saved: boolean) => void }) {
  const { logout } = useAuth()
  const reset = useResetPassword()
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [copied, setCopied] = useState(false)
  const tooShort = password.length < MIN_LENGTH

  const generate = () => {
    setPassword(generatePassword())
    setVisible(true)
    setCopied(false)
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(password)
      setCopied(true)
    } catch {
      setVisible(true)   // no clipboard access: at least show it so it can be copied by hand
    }
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (tooShort) return
    reset.mutate({ userId: user.id, password }, {
      onSuccess: () => (isSelf ? logout() : onDone(true)),   // your own token stops working too
    })
  }

  return (
    <form className="stack user-reset" onSubmit={submit}>
      <label>
        <span>New password for <strong>{user.username}</strong></span>
        <span className="row wrap user-reset-input">
          <input
            type={visible ? 'text' : 'password'}
            value={password}
            onChange={(e) => { setPassword(e.target.value); setCopied(false) }}
            minLength={MIN_LENGTH}
            maxLength={128}
            autoComplete="new-password"
            autoFocus
            required
          />
          <button type="button" className="ghost small" onClick={() => setVisible(!visible)}>{visible ? 'Hide' : 'Show'}</button>
          <button type="button" className="ghost small" onClick={generate}>Generate</button>
          <button type="button" className="ghost small" onClick={copy} disabled={!password}>{copied ? 'Copied' : 'Copy'}</button>
        </span>
      </label>
      <p className="small muted">
        At least {MIN_LENGTH} characters. Saving signs {isSelf ? 'you' : user.username} out on every device; send them the new password yourself.
      </p>
      {isSelf && <div className="notice notice-warn">This is your own account: you will be signed out and need to log in with the new password.</div>}
      <ErrorNotice error={reset.error} />
      <div className="row wrap">
        <button className="primary" disabled={tooShort || reset.isPending}>{reset.isPending ? 'Saving…' : 'Save new password'}</button>
        <button type="button" className="ghost" onClick={() => onDone(false)}>Cancel</button>
      </div>
    </form>
  )
}

/** Every site user, with a password reset: a stopgap until users can recover their own accounts. */
export default function UsersPage() {
  const users = useAdminUsers()
  const { user: me } = useAuth()
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [savedFor, setSavedFor] = useState<string | null>(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = users.data ?? []
    return q ? all.filter((u) => u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)) : all
  }, [users.data, query])

  if (users.isLoading) return <Loading label="Loading users…" />

  return (
    <div className="card stack">
      <div className="row between wrap">
        <h1>Users</h1>
        <span className="badge">{users.data?.length ?? 0} total</span>
      </div>
      <p className="muted small">Reset a password for someone who is locked out. Until password recovery exists, this is the only way back in.</p>
      <ErrorNotice error={users.error} />
      {savedFor && <div className="notice">Password changed. {savedFor} has been signed out everywhere; send them the new password.</div>}
      <input type="search" placeholder="Search by username or email" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search users" />
      <div className="table-scroll">
        <table className="compact users-table">
          <thead>
            <tr>
              <th>Username</th><th>Email</th><th>Joined</th>
              <th className="num">Teams</th><th className="num">Players</th><th className="num">Games</th>
              <th>Password changed</th><th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <UserRow
                key={u.id}
                user={u}
                isSelf={u.id === me?.id}
                editing={editing === u.id}
                onEdit={() => { setEditing(u.id); setSavedFor(null) }}
                onDone={(saved) => { setEditing(null); if (saved) setSavedFor(u.username) }}
              />
            ))}
            {rows.length === 0 && <tr><td colSpan={8} className="muted">No users match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function UserRow({ user, isSelf, editing, onEdit, onDone }: {
  user: AdminUser; isSelf: boolean; editing: boolean; onEdit: () => void; onDone: (saved: boolean) => void
}) {
  return (
    <>
      <tr>
        <td>{user.username}{user.is_admin && <span className="badge gold">Admin</span>}{isSelf && <span className="badge">You</span>}</td>
        <td className="users-email">{user.email}</td>
        <td>{day(user.created_at)}</td>
        <td className="num">{user.teams}</td>
        <td className="num">{user.players}</td>
        <td className="num">{user.games}</td>
        <td>{day(user.password_changed_at)}</td>
        <td>{!editing && <button className="ghost small" onClick={onEdit}>Reset password</button>}</td>
      </tr>
      {editing && (
        <tr className="user-reset-row">
          <td colSpan={8}><ResetForm user={user} isSelf={isSelf} onDone={onDone} /></td>
        </tr>
      )}
    </>
  )
}
