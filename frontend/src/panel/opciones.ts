import { useEffect, useState } from 'react'
import { api } from '../lib/api'

let pendiente: Promise<boolean> | null = null

/** Si la empresa ha activado los costes en euros. Sin permiso o sin respuesta: oculto. */
export function useMostrarCostes(): boolean {
  const [mostrar, setMostrar] = useState(false)
  useEffect(() => {
    let vivo = true
    pendiente ??= api
      .getOpcionesPanel()
      .then((o) => o.mostrar_costes)
      .catch(() => false)
    pendiente.then((v) => {
      if (vivo) setMostrar(v)
    })
    return () => {
      vivo = false
    }
  }, [])
  return mostrar
}

/** Para pruebas y para volver a leer la opción tras cambiarla. */
export function reiniciarOpciones() {
  pendiente = null
}
