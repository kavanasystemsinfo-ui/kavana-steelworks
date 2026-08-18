import { useEffect, useState } from 'react'

/** Tipos de la API de administración (spec 07, ADR-015). */

interface TenantOut {
  id: string
  name: string
  slug: string
  status: string
  is_active: boolean
  auth: Record<string, unknown>
  theme: Record<string, unknown>
  finances: Record<string, unknown>
  sequences_config: Record<string, unknown>
}

interface UserOut {
  id: string
  email: string
  name: string
  role: string
  is_active: boolean
  employee_number: string | null
  default_workstation_code: string | null
  last_login_at: string | null
}

interface SeqCfg {
  prefix: string
  padding: number
}

interface SequencesOut {
  order: SeqCfg
  lot: SeqCfg
}

interface WorkstationOut {
  id: string
  group_id: string | null
  code: string
  name: string
  color: string
  hourly_cost: number
  registration_method: string
  maintenance_interval_hours: number
  maintenance_pre_warning_hours: number
  last_maintenance_reset: string | null
  accumulated_hours: number
  is_active: boolean
}

interface WorkstationGroupOut {
  id: string
  name: string
  color: string
}

interface RoleOut {
  id: string
  role_key: string
  name: string
  permissions: string[]
  is_system: boolean
}

const inputCls =
  'mono-data mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 min-h-[48px] text-kavana-text focus:border-kavana-orange outline-none'

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="label-industrial text-xs text-kavana-text-dim">{label}</span>
      {children}
    </label>
  )
}

function Button({
  children,
  variant = 'primary',
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger'
}) {
  const base =
    'px-4 py-2 text-sm uppercase tracking-wider rounded-sm transition-colors disabled:opacity-40'
  const styles = {
    primary: 'bg-kavana-orange text-black font-bold hover:opacity-90',
    ghost:
      'border border-kavana-border text-kavana-text-dim hover:text-kavana-text hover:border-kavana-orange',
    danger:
      'border border-red-500/50 text-red-400 hover:bg-red-500/10',
  }
  return (
    <button className={`${base} ${styles[variant]}`} {...rest}>
      {children}
    </button>
  )
}

function PanelCard({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="bg-kavana-surface border border-kavana-border rounded-sm p-6 space-y-4">
      <h2 className="label-industrial text-kavana-orange text-sm">{title}</h2>
      {children}
    </section>
  )
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1/admin${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Error ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** Pestaña Empresa: nombre, slug, estado y JSONs de configuración. */
function EmpresaTab() {
  const [tenant, setTenant] = useState<TenantOut | null>(null)
  const [form, setForm] = useState({
    name: '',
    slug: '',
    status: 'active',
    primaryColor: '#e56b2e',
    companyName: '',
    overhead: 0,
  })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    apiFetch<TenantOut>('/tenant')
      .then((t) => {
        setTenant(t)
        setForm({
          name: t.name,
          slug: t.slug,
          status: t.status,
          primaryColor:
            (t.theme.colors as Record<string, string> | undefined)?.primary ??
            '#e56b2e',
          companyName:
            (t.theme.branding as Record<string, string> | undefined)
              ?.companyName ?? '',
          overhead:
            (t.finances.overhead_hourly_cost as number | undefined) ?? 0,
        })
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al cargar empresa'))
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    setMsg('')
    const theme = {
      ...(tenant?.theme ?? {}),
      colors: { primary: form.primaryColor },
      branding: { companyName: form.companyName, logoUrl: '' },
    }
    const finances = { ...(tenant?.finances ?? {}), overhead_hourly_cost: Number(form.overhead) }
    try {
      const updated = await apiFetch<TenantOut>('/tenant', {
        method: 'PUT',
        body: JSON.stringify({
          name: form.name,
          slug: form.slug,
          status: form.status,
          theme,
          finances,
        }),
      })
      setTenant(updated)
      setMsg('Empresa actualizada')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al guardar')
    }
  }

  return (
    <PanelCard title="Empresa">
      {tenant === null ? (
        <p className="text-kavana-text-dim text-sm">Cargando…</p>
      ) : (
        <form onSubmit={handleSave} className="grid grid-cols-2 gap-4">
          <Field label="Nombre">
            <input
              className={inputCls}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Slug (identificador URL)">
            <input
              className={inputCls}
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
            />
          </Field>
          <Field label="Estado">
            <select
              className={inputCls}
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="active">active</option>
              <option value="trial">trial</option>
              <option value="suspended">suspended</option>
            </select>
          </Field>
          <Field label="Color principal">
            <input
              type="color"
              className="mt-1 w-full h-[48px] bg-kavana-dark border border-kavana-border rounded-sm"
              value={form.primaryColor}
              onChange={(e) => setForm({ ...form, primaryColor: e.target.value })}
            />
          </Field>
          <Field label="Nombre mostrado (branding)">
            <input
              className={inputCls}
              value={form.companyName}
              onChange={(e) => setForm({ ...form, companyName: e.target.value })}
            />
          </Field>
          <Field label="Coste global mano de obra (€/h)">
            <input
              type="number"
              step="0.01"
              className={inputCls}
              value={form.overhead}
              onChange={(e) => setForm({ ...form, overhead: Number(e.target.value) })}
            />
          </Field>
          <div className="col-span-2 flex items-center gap-3">
            <Button type="submit">Guardar</Button>
            {msg && <span className="text-kavana-ok text-sm">{msg}</span>}
            {err && <span className="text-red-400 text-sm">{err}</span>}
          </div>
        </form>
      )}
    </PanelCard>
  )
}

/** Pestaña Usuarios: listado + crear + editar rol/estado/password. */
function UsuariosTab() {
  const [users, setUsers] = useState<UserOut[]>([])
  const [form, setForm] = useState({
    email: '',
    name: '',
    password: '',
    role: 'operator',
    employee_number: '',
    default_workstation_code: '',
  })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [editing, setEditing] = useState<UserOut | null>(null)
  const [editPassword, setEditPassword] = useState('')

  const load = () => {
    apiFetch<UserOut[]>('/users')
      .then(setUsers)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al cargar usuarios'))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    setMsg('')
    try {
      await apiFetch<UserOut>('/users', {
        method: 'POST',
        body: JSON.stringify({
          email: form.email,
          name: form.name,
          password: form.password,
          role: form.role,
          employee_number: form.employee_number || null,
          default_workstation_code: form.default_workstation_code || null,
        }),
      })
      setMsg(`Usuario ${form.email} creado`)
      setForm({ email: '', name: '', password: '', role: 'operator', employee_number: '', default_workstation_code: '' })
      load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al crear usuario')
    }
  }

  const updateUser = async (id: string, patch: Record<string, unknown>, revert: () => void) => {
    setErr('')
    setMsg('')
    try {
      await apiFetch<UserOut>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      setMsg('Usuario actualizado')
      load()
    } catch (e) {
      revert()
      setErr(e instanceof Error ? e.message : 'Error al actualizar usuario')
    }
  }

  const toggleActive = (u: UserOut) => {
    updateUser(u.id, { is_active: !u.is_active }, () => undefined)
  }

  const saveEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editing) return
    const patch: Record<string, unknown> = {
      role: editing.role,
      employee_number: editing.employee_number || null,
      default_workstation_code: editing.default_workstation_code || null,
    }
    if (editPassword) patch.password = editPassword
    const prev = editing
    await updateUser(editing.id, patch, () => setEditing(prev))
    setEditing(null)
    setEditPassword('')
  }

  const deactivate = (u: UserOut) => {
    setErr('')
    setMsg('')
    apiFetch<UserOut>(`/users/${u.id}`, { method: 'DELETE' })
      .then(() => {
        setMsg(`Usuario ${u.email} desactivado`)
        load()
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al desactivar'))
  }

  return (
    <PanelCard title="Usuarios">
      <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4 border-b border-kavana-border pb-4">
        <Field label="Email">
          <input className={inputCls} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </Field>
        <Field label="Nombre">
          <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="Password inicial">
          <input type="password" className={inputCls} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </Field>
        <Field label="Rol">
          <select className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="operator">operator</option>
            <option value="supervisor">supervisor</option>
            <option value="materials">materials</option>
            <option value="admin">admin</option>
          </select>
        </Field>
        <Field label="Nº empleado (opcional)">
          <input className={inputCls} value={form.employee_number} onChange={(e) => setForm({ ...form, employee_number: e.target.value })} />
        </Field>
        <Field label="Puesto por defecto (código)">
          <input className={inputCls} value={form.default_workstation_code} onChange={(e) => setForm({ ...form, default_workstation_code: e.target.value })} />
        </Field>
        <div className="col-span-2 flex items-center gap-3">
          <Button type="submit">Crear usuario</Button>
          {msg && <span className="text-kavana-ok text-sm">{msg}</span>}
          {err && <span className="text-red-400 text-sm">{err}</span>}
        </div>
      </form>

      <div className="space-y-2">
        {users.map((u) => (
          <div key={u.id} className="border border-kavana-border rounded-sm p-3 flex flex-wrap items-center gap-3">
            <span className="mono-data text-sm">{u.email}</span>
            <span className="text-xs uppercase tracking-wider px-2 py-0.5 bg-kavana-dark border border-kavana-border rounded-sm">
              {u.role}
            </span>
            <span className={`text-xs ${u.is_active ? 'text-kavana-ok' : 'text-red-400'}`}>
              {u.is_active ? 'activo' : 'inactivo'}
            </span>
            {u.default_workstation_code && (
              <span className="text-xs text-kavana-text-dim">{u.default_workstation_code}</span>
            )}
            <div className="ml-auto flex items-center gap-2">
              <Button variant="ghost" onClick={() => { setEditing(u); setEditPassword('') }}>
                Editar
              </Button>
              <Button variant="danger" onClick={() => toggleActive(u)}>
                {u.is_active ? 'Desactivar' : 'Activar'}
              </Button>
              <Button variant="ghost" onClick={() => deactivate(u)}>Eliminar</Button>
            </div>
          </div>
        ))}
      </div>

      {editing && (
        <form onSubmit={saveEdit} className="border border-kavana-orange/40 rounded-sm p-4 space-y-3">
          <p className="label-industrial text-kavana-orange text-xs">Editar {editing.email}</p>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Rol">
              <select className={inputCls} value={editing.role} onChange={(e) => setEditing({ ...editing, role: e.target.value })}>
                <option value="operator">operator</option>
                <option value="supervisor">supervisor</option>
                <option value="materials">materials</option>
                <option value="admin">admin</option>
              </select>
            </Field>
            <Field label="Nueva password (opcional)">
              <input type="password" className={inputCls} value={editPassword} onChange={(e) => setEditPassword(e.target.value)} />
            </Field>
            <Field label="Nº empleado">
              <input className={inputCls} value={editing.employee_number ?? ''} onChange={(e) => setEditing({ ...editing, employee_number: e.target.value })} />
            </Field>
            <Field label="Puesto por defecto">
              <input className={inputCls} value={editing.default_workstation_code ?? ''} onChange={(e) => setEditing({ ...editing, default_workstation_code: e.target.value })} />
            </Field>
          </div>
          <div className="flex gap-3">
            <Button type="submit">Guardar cambios</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancelar</Button>
          </div>
        </form>
      )}
    </PanelCard>
  )
}

/** Pestaña Secuencias: prefix/padding por tipo + vista del siguiente número. */
function SecuenciasTab() {
  const [cfg, setCfg] = useState<SequencesOut | null>(null)
  const [nextOrder, setNextOrder] = useState('')
  const [nextLot, setNextLot] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    apiFetch<SequencesOut>('/sequences')
      .then(setCfg)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al cargar secuencias'))
  }, [])

  const refreshNext = () => {
    apiFetch<{ type: string; next: string }>('/sequences/next/order')
      .then((r) => setNextOrder(r.next))
      .catch(() => setNextOrder('—'))
    apiFetch<{ type: string; next: string }>('/sequences/next/lot')
      .then((r) => setNextLot(r.next))
      .catch(() => setNextLot('—'))
  }

  useEffect(() => {
    if (cfg) refreshNext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!cfg) return
    setErr('')
    setMsg('')
    try {
      const updated = await apiFetch<SequencesOut>('/sequences', {
        method: 'PUT',
        body: JSON.stringify(cfg),
      })
      setCfg(updated)
      setMsg('Configuración de secuencias guardada')
      refreshNext()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al guardar')
    }
  }

  const setField = (kind: keyof SequencesOut, field: keyof SeqCfg, value: string | number) => {
    if (!cfg) return
    setCfg({
      ...cfg,
      [kind]: { ...cfg[kind], [field]: field === 'padding' ? Number(value) : value },
    })
  }

  return (
    <PanelCard title="Secuencias automáticas (órdenes y lotes)">
      {cfg === null ? (
        <p className="text-kavana-text-dim text-sm">Cargando…</p>
      ) : (
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-4 gap-4">
            <Field label="Tipo">
              <input className={inputCls} value="Órdenes (OP)" disabled />
            </Field>
            <Field label="Prefijo">
              <input className={inputCls} value={cfg.order.prefix} onChange={(e) => setField('order', 'prefix', e.target.value)} />
            </Field>
            <Field label="Padding (dígitos)">
              <input type="number" min={1} max={10} className={inputCls} value={cfg.order.padding} onChange={(e) => setField('order', 'padding', e.target.value)} />
            </Field>
            <Field label="Siguiente número">
              <input className={inputCls} value={nextOrder || '—'} disabled />
            </Field>
            <Field label="Tipo">
              <input className={inputCls} value="Lotes (LT)" disabled />
            </Field>
            <Field label="Prefijo">
              <input className={inputCls} value={cfg.lot.prefix} onChange={(e) => setField('lot', 'prefix', e.target.value)} />
            </Field>
            <Field label="Padding (dígitos)">
              <input type="number" min={1} max={10} className={inputCls} value={cfg.lot.padding} onChange={(e) => setField('lot', 'padding', e.target.value)} />
            </Field>
            <Field label="Siguiente número">
              <input className={inputCls} value={nextLot || '—'} disabled />
            </Field>
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit">Guardar</Button>
            <Button type="button" variant="ghost" onClick={refreshNext}>Ver siguiente</Button>
            {msg && <span className="text-kavana-ok text-sm">{msg}</span>}
            {err && <span className="text-red-400 text-sm">{err}</span>}
          </div>
        </form>
      )}
    </PanelCard>
  )
}

/** Pestaña Puestos: listar, crear, editar, desactivar. */
function PuestosTab() {
  const [wss, setWss] = useState<WorkstationOut[]>([])
  const [groups, setGroups] = useState<WorkstationGroupOut[]>([])
  const [form, setForm] = useState({
    code: '',
    name: '',
    color: '#3498db',
    hourly_cost: 0,
    registration_method: 'quantity',
    group_id: '',
    maintenance_interval_hours: 0,
  })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = () => {
    apiFetch<WorkstationOut[]>('/workstations')
      .then(setWss)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al cargar puestos'))
    apiFetch<WorkstationGroupOut[]>('/workstations/groups')
      .then(setGroups)
      .catch(() => undefined)
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    setMsg('')
    try {
      await apiFetch<WorkstationOut>('/workstations', {
        method: 'POST',
        body: JSON.stringify({
          code: form.code,
          name: form.name,
          color: form.color,
          hourly_cost: Number(form.hourly_cost),
          registration_method: form.registration_method,
          maintenance_interval_hours: Number(form.maintenance_interval_hours),
          group_id: form.group_id || null,
        }),
      })
      setMsg(`Puesto ${form.code} creado`)
      setForm({ ...form, code: '', name: '' })
      load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al crear puesto')
    }
  }

  const toggleActive = (w: WorkstationOut) => {
    apiFetch<WorkstationOut>(`/workstations/${w.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !w.is_active }),
    })
      .then(() => load())
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al actualizar puesto'))
  }

  const deactivate = (w: WorkstationOut) => {
    apiFetch<WorkstationOut>(`/workstations/${w.id}`, { method: 'DELETE' })
      .then(() => {
        setMsg(`Puesto ${w.code} desactivado`)
        load()
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al desactivar puesto'))
  }

  return (
    <PanelCard title="Puestos de trabajo">
      <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4 border-b border-kavana-border pb-4">
        <Field label="Código (ej. LINEA-4)">
          <input className={inputCls} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
        </Field>
        <Field label="Nombre">
          <input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="Método de registro">
          <select className={inputCls} value={form.registration_method} onChange={(e) => setForm({ ...form, registration_method: e.target.value })}>
            <option value="quantity">quantity</option>
            <option value="timer">timer</option>
            <option value="manual">manual</option>
          </select>
        </Field>
        <Field label="Coste hora (€)">
          <input type="number" step="0.01" className={inputCls} value={form.hourly_cost} onChange={(e) => setForm({ ...form, hourly_cost: Number(e.target.value) })} />
        </Field>
        <Field label="Grupo">
          <select className={inputCls} value={form.group_id} onChange={(e) => setForm({ ...form, group_id: e.target.value })}>
            <option value="">Sin grupo</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Intervalo mantenimiento (h, 0 = off)">
          <input type="number" min={0} className={inputCls} value={form.maintenance_interval_hours} onChange={(e) => setForm({ ...form, maintenance_interval_hours: Number(e.target.value) })} />
        </Field>
        <div className="col-span-2 flex items-center gap-3">
          <Button type="submit">Crear puesto</Button>
          {msg && <span className="text-kavana-ok text-sm">{msg}</span>}
          {err && <span className="text-red-400 text-sm">{err}</span>}
        </div>
      </form>

      <div className="space-y-2">
        {wss.map((w) => (
          <div key={w.id} className="border border-kavana-border rounded-sm p-3 flex flex-wrap items-center gap-3">
            <span className="mono-data text-sm">{w.code}</span>
            <span className="text-sm">{w.name}</span>
            <span className={`w-4 h-4 rounded-sm inline-block`} style={{ backgroundColor: w.color }} />
            <span className="text-xs text-kavana-text-dim">{w.registration_method} · {w.hourly_cost} €/h</span>
            <span className={`text-xs ${w.is_active ? 'text-kavana-ok' : 'text-red-400'}`}>
              {w.is_active ? 'activo' : 'inactivo'}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <Button variant="ghost" onClick={() => toggleActive(w)}>
                {w.is_active ? 'Desactivar' : 'Activar'}
              </Button>
              <Button variant="ghost" onClick={() => deactivate(w)}>Eliminar</Button>
            </div>
          </div>
        ))}
      </div>
    </PanelCard>
  )
}

/** Pestaña Roles: ver permisos por rol; editar solo roles custom. */
const PERMISOS_CATALOGO = [
  'stock.scan', 'stock.link', 'stock.finish', 'stock.receive', 'stock.list',
  'production.record', 'quality.check', 'quality.read', 'incidencia.create',
  'incidencia.manage', 'oee.read', 'trace.read', 'orders.read', 'admin.users',
  'admin.tenant', 'admin.sequences', 'admin.workstations', 'admin.roles',
]

function RolesTab() {
  const [roles, setRoles] = useState<RoleOut[]>([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [editKey, setEditKey] = useState<string | null>(null)
  const [editPerms, setEditPerms] = useState<string[]>([])

  const load = () => {
    apiFetch<RoleOut[]>('/roles')
      .then(setRoles)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error al cargar roles'))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startEdit = (r: RoleOut) => {
    setEditKey(r.role_key)
    setEditPerms(r.permissions)
  }

  const saveEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editKey) return
    setErr('')
    setMsg('')
    try {
      await apiFetch<RoleOut>(`/roles/${editKey}`, {
        method: 'PUT',
        body: JSON.stringify({ permissions: editPerms }),
      })
      setMsg('Permisos actualizados')
      setEditKey(null)
      load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al guardar permisos')
    }
  }

  return (
    <PanelCard title="Roles y permisos">
      <div className="space-y-2">
        {roles.map((r) => (
          <div key={r.id} className="border border-kavana-border rounded-sm p-3">
            <div className="flex items-center gap-3">
              <span className="mono-data text-sm">{r.role_key}</span>
              <span className="text-sm">{r.name}</span>
              {r.is_system && (
                <span className="text-xs uppercase tracking-wider px-2 py-0.5 bg-kavana-dark border border-kavana-border rounded-sm text-kavana-text-dim">
                  sistema
                </span>
              )}
              {!r.is_system && editKey !== r.role_key && (
                <Button variant="ghost" onClick={() => startEdit(r)} className="ml-auto">
                  Editar permisos
                </Button>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {r.permissions.map((p) => (
                <span key={p} className="text-xs px-2 py-0.5 bg-kavana-dark border border-kavana-border rounded-sm font-mono">
                  {p}
                </span>
              ))}
            </div>
            {editKey === r.role_key && (
              <form onSubmit={saveEdit} className="mt-3 border-t border-kavana-border pt-3">
                <div className="grid grid-cols-3 gap-1">
                  {PERMISOS_CATALOGO.map((p) => (
                    <label key={p} className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editPerms.includes(p)}
                        onChange={(e) =>
                          setEditPerms((prev) =>
                            e.target.checked ? [...prev, p] : prev.filter((x) => x !== p),
                          )
                        }
                      />
                      <span className="font-mono">{p}</span>
                    </label>
                  ))}
                </div>
                <div className="flex gap-3 mt-3">
                  <Button type="submit">Guardar</Button>
                  <Button type="button" variant="ghost" onClick={() => setEditKey(null)}>Cancelar</Button>
                </div>
              </form>
            )}
          </div>
        ))}
      </div>
      {msg && <p className="text-kavana-ok text-sm">{msg}</p>}
      {err && <p className="text-red-400 text-sm">{err}</p>}
    </PanelCard>
  )
}

/** Panel de Administración (spec 07): solo rol admin (matriz Fase 6). */
export function AdminPage() {
  const [tab, setTab] = useState<
    'empresa' | 'usuarios' | 'secuencias' | 'puestos' | 'roles'
  >('empresa')

  const tabs = [
    { id: 'empresa' as const, label: 'Empresa', icon: '🏭' },
    { id: 'usuarios' as const, label: 'Usuarios', icon: '👤' },
    { id: 'secuencias' as const, label: 'Secuencias', icon: '🔢' },
    { id: 'puestos' as const, label: 'Puestos', icon: '🛠️' },
    { id: 'roles' as const, label: 'Roles', icon: '🔐' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-kavana-border pb-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm uppercase tracking-wider rounded-sm transition-colors ${
              tab === t.id
                ? 'bg-kavana-orange text-black font-bold'
                : 'text-kavana-text-dim hover:text-kavana-text'
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>
      {tab === 'empresa' && <EmpresaTab />}
      {tab === 'usuarios' && <UsuariosTab />}
      {tab === 'secuencias' && <SecuenciasTab />}
      {tab === 'puestos' && <PuestosTab />}
      {tab === 'roles' && <RolesTab />}
    </div>
  )
}