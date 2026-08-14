import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { OperarioPage } from './pages/OperarioPage'
import { MateriasPrimasPage } from './pages/MateriasPrimasPage'
import { SupervisorPage } from './pages/SupervisorPage'
import { Layout } from './components/layout/Layout'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/operario" element={<OperarioPage />} />
        <Route path="/materias-primas" element={<MateriasPrimasPage />} />
        <Route path="/supervisor" element={<SupervisorPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/operario" replace />} />
    </Routes>
  )
}
