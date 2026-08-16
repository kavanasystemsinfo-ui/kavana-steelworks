import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { MobilePhotoUpload } from './pages/MobilePhotoUpload'
import { OperarioPage } from './pages/OperarioPage'
import { MateriasPrimasPage } from './pages/MateriasPrimasPage'
import { SupervisorPage } from './pages/SupervisorPage'
import { Layout } from './components/layout/Layout'
import { getJwtPayload } from './lib/api'
import { HOME_BY_ROLE, canAccess, type Role } from './lib/roles'

/** Ruta pública del móvil: /mobile-upload/:sessionId (sin Layout). */
function MobileUploadRoute() {
  const { sessionId } = useParams()
  if (!sessionId) return <Navigate to="/login" replace />
  return <MobilePhotoUpload sessionId={sessionId} />
}

function currentRole(): Role | null {
  const payload = getJwtPayload()
  if (!payload?.role) return null
  return payload.role as Role
}

/**
 * Guard de autenticación + rol. Sin token → /login. Con token pero sin
 * acceso al panel → su home según rol. La ruta pública del móvil va aparte.
 */
function RequireRole({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const role = currentRole()
  if (!role) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (!canAccess(role, location.pathname)) {
    return <Navigate to={HOME_BY_ROLE[role]} replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/mobile-upload/:sessionId" element={<MobileUploadRoute />} />
      <Route
        element={
          <RequireRole>
            <Layout />
          </RequireRole>
        }
      >
        <Route path="/operario" element={<OperarioPage />} />
        <Route path="/materias-primas" element={<MateriasPrimasPage />} />
        <Route path="/supervisor" element={<SupervisorPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
