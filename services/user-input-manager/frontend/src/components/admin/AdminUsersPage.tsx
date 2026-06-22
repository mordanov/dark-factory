import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usersApi, extractError, type User } from '../../api/client'

interface EditState {
  userId: string
  email: string
  full_name: string
  is_admin: boolean
  password: string
}

function emptyEdit(u: User): EditState {
  return { userId: u.id, email: u.email, full_name: u.full_name, is_admin: u.is_admin, password: '' }
}

export function AdminUsersPage() {
  const { t } = useTranslation()

  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editState, setEditState] = useState<EditState | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createState, setCreateState] = useState({ email: '', full_name: '', password: '', is_admin: false })
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await usersApi.list()
      setUsers(data.items)
      setTotal(data.total)
    } catch (err) {
      setError(extractError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleToggleActive = async (u: User) => {
    setSaving(true)
    try {
      await usersApi.update(u.id, { is_active: !u.is_active })
      await load()
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editState) return
    setSaving(true)
    try {
      const payload: any = {
        email: editState.email,
        full_name: editState.full_name,
        is_admin: editState.is_admin,
      }
      if (editState.password) payload.password = editState.password
      await usersApi.update(editState.userId, payload)
      setEditState(null)
      await load()
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await usersApi.create(createState)
      setShowCreate(false)
      setCreateState({ email: '', full_name: '', password: '', is_admin: false })
      await load()
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('admin.title')}</h1>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          + {t('admin.create_user')}
        </button>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {/* Create user modal */}
      {showCreate && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setShowCreate(false)}>
          <div className="modal">
            <h2 className="modal-title">{t('admin.create_user')}</h2>
            <form onSubmit={handleCreate} className="flex flex-col gap-16">
              <div className="form-group">
                <label>{t('admin.email')}</label>
                <input type="email" value={createState.email} onChange={e => setCreateState(s => ({ ...s, email: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label>{t('admin.full_name')}</label>
                <input value={createState.full_name} onChange={e => setCreateState(s => ({ ...s, full_name: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>{t('admin.password')}</label>
                <input type="password" value={createState.password} onChange={e => setCreateState(s => ({ ...s, password: e.target.value }))} required minLength={8} />
              </div>
              <div className="flex gap-8" style={{ alignItems: 'center' }}>
                <input type="checkbox" id="is-admin" checked={createState.is_admin} onChange={e => setCreateState(s => ({ ...s, is_admin: e.target.checked }))} style={{ width: 'auto' }} />
                <label htmlFor="is-admin" style={{ textTransform: 'none', letterSpacing: 0 }}>{t('admin.admin')}</label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>{t('admin.cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? <span className="spinner" /> : t('admin.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit user modal */}
      {editState && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setEditState(null)}>
          <div className="modal">
            <h2 className="modal-title">{t('admin.edit')}</h2>
            <form onSubmit={handleSaveEdit} className="flex flex-col gap-16">
              <div className="form-group">
                <label>{t('admin.email')}</label>
                <input type="email" value={editState.email} onChange={e => setEditState(s => s && ({ ...s, email: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label>{t('admin.full_name')}</label>
                <input value={editState.full_name} onChange={e => setEditState(s => s && ({ ...s, full_name: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>{t('admin.password')}</label>
                <input type="password" value={editState.password} onChange={e => setEditState(s => s && ({ ...s, password: e.target.value }))} placeholder={t('admin.password_hint')} minLength={8} />
              </div>
              <div className="flex gap-8" style={{ alignItems: 'center' }}>
                <input type="checkbox" id="edit-is-admin" checked={editState.is_admin} onChange={e => setEditState(s => s && ({ ...s, is_admin: e.target.checked }))} style={{ width: 'auto' }} />
                <label htmlFor="edit-is-admin" style={{ textTransform: 'none', letterSpacing: 0 }}>{t('admin.admin')}</label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setEditState(null)}>{t('admin.cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? <span className="spinner" /> : t('admin.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {loading ? (
        <div className="empty-state"><span className="spinner" /></div>
      ) : users.length === 0 ? (
        <div className="empty-state">{t('admin.empty')}</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="sessions-table">
            <thead>
              <tr>
                <th>{t('admin.email')}</th>
                <th>{t('admin.full_name')}</th>
                <th>{t('admin.role')}</th>
                <th>{t('admin.status')}</th>
                <th>{t('admin.created')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} onClick={() => {}} style={{ cursor: 'default' }}>
                  <td className="mono" style={{ fontSize: '0.8rem' }}>{u.email}</td>
                  <td>{u.full_name || '—'}</td>
                  <td>
                    <span className={`badge ${u.is_admin ? 'badge-amber' : 'badge-muted'}`}>
                      {u.is_admin ? t('admin.admin') : t('admin.user')}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${u.is_active ? 'badge-green' : 'badge-red'}`}>
                      {u.is_active ? t('admin.active') : t('admin.blocked')}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: '0.75rem' }}>
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <div className="flex gap-8">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => setEditState(emptyEdit(u))}
                      >
                        {t('admin.edit')}
                      </button>
                      <button
                        className={`btn btn-sm ${u.is_active ? 'btn-danger' : 'btn-secondary'}`}
                        onClick={() => handleToggleActive(u)}
                        disabled={saving}
                      >
                        {u.is_active ? t('admin.block') : t('admin.unblock')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
