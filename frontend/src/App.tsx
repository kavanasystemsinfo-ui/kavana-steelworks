import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { MobilePhotoUpload } from './pages/MobilePhotoUpload'
import { OperarioPage } from './pages/OperarioPage'
import { MateriasPrimasPage } from './pages/MateriasPrimasPage'
import { SupervisorPage } from './pages/SupervisorPage'
import { Layout } from './components/layout/Layout'

/** Ruta pública del móvil: /mobile-upload/:sessionId (sin Layout). */
function MobileUploadRoute() {
  const { sessionId } = useParams()
  if (!sessionId) return <Navigate to="/operario" replace />
  return <MobilePhotoUpload sessionId={sessionId} />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/mobile-upload/:sessionId" element={<MobileUploadRoute />} />
      <Route element={<Layout />}>
        <Route path="/operario" element={<OperarioPage />} />
        <Route path="/materias-primas" element={<MateriasPrimasPage />} />
        <Route path="/supervisor" element={<SupervisorPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/operario" replace />} />
    </Routes>
  )
}
