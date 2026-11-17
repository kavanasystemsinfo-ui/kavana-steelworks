import { useEffect, useMemo, useRef, useState } from 'react'
import { Tour, type TourStep } from './Tour'

/**
 * Hook del tour: varios recorridos (uno por pantalla) y un único componente.
 * El componente que devuelve tiene identidad estable: si cambiara en cada
 * repintado del panel, React lo desmontaría y el tour volvería al paso 1.
 */
export function useTour(tours: Record<string, TourStep[]>, claveVisto: string) {
  const [isOpen, setIsOpen] = useState(false)
  const [clave, setClave] = useState<string>('operario')
  const toursRef = useRef(tours)
  const claveVistoRef = useRef(claveVisto)
  useEffect(() => {
    toursRef.current = tours
    claveVistoRef.current = claveVisto
  })

  const start = (nueva?: string) => {
    if (nueva) setClave(nueva)
    setIsOpen(true)
  }
  const close = () => setIsOpen(false)
  const complete = () => {
    try {
      localStorage.setItem(claveVistoRef.current, 'true')
    } catch {
      /* sin almacenamiento: da igual */
    }
    setIsOpen(false)
  }

  const TourComponent = useMemo(
    () =>
      function TourDelPanel(props: {
        isOpen: boolean
        clave: string
        onClose: () => void
        onComplete: () => void
        onIr: (clave: string) => void
      }) {
        const { clave: claveTour, ...resto } = props
        // Solo existe mientras está abierto, y con key por tour: cada vez empieza en su paso 1.
        if (!resto.isOpen) return null
        return <Tour key={claveTour} steps={toursRef.current[claveTour] ?? []} {...resto} />
      },
    [],
  )

  const tourProps = {
    isOpen,
    clave,
    onClose: close,
    onComplete: complete,
    onIr: (siguiente: string) => setClave(siguiente),
  }

  return { isOpen, start, close, complete, TourComponent, tourProps }
}
