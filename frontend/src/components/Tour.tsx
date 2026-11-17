import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export interface TourStep {
  id: string
  /**
   * Selector(es) CSS del elemento que se resalta. Con varios, se resalta el
   * rectángulo que los abarca. Sin ancla, el paso sale centrado.
   */
  anchor?: string | string[]
  title: string
  content: string
  /** Se ejecuta al llegar al paso (por ejemplo, abrir la pantalla que se explica). */
  action?: () => void
  /**
   * Paso final que ofrece seguir con otro tour (clave del tour siguiente): en vez
   * de «Siguiente» enseña «No, omitir» y «Sí, llévame».
   */
  siguiente?: string
}

interface TourProps {
  steps: TourStep[]
  isOpen: boolean
  onClose: () => void
  onComplete: () => void
  /** Pasa al tour de otra pantalla (lo pide el paso final con `siguiente`). */
  onIr: (clave: string) => void
}

const ANCHO_TOOLTIP = 380
const ALTO_TOOLTIP = 300
const HUECO = 12
/** Cuánto se espera a que aparezca el elemento tras cambiar de pantalla (incluye la carga de datos del servidor). */
const ESPERA_MAXIMA_MS = 12000

function buscarAncla(anchor: string | string[] | undefined): HTMLElement[] {
  if (!anchor) return []
  const selectores = Array.isArray(anchor) ? anchor : [anchor]
  const encontrados: HTMLElement[] = []
  for (const selector of selectores) {
    let candidatos: HTMLElement[] = []
    try {
      candidatos = Array.from(document.querySelectorAll<HTMLElement>(selector))
    } catch {
      candidatos = []
    }
    for (const el of candidatos) {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.height > 0) {
        encontrados.push(el)
        break
      }
    }
  }
  return encontrados
}

/** Rectángulo que abarca a todos los elementos. */
function abarcar(elementos: HTMLElement[]): DOMRect {
  const rects = elementos.map((e) => e.getBoundingClientRect())
  const left = Math.min(...rects.map((r) => r.left))
  const top = Math.min(...rects.map((r) => r.top))
  const right = Math.max(...rects.map((r) => r.right))
  const bottom = Math.max(...rects.map((r) => r.bottom))
  return new DOMRect(left, top, right - left, bottom - top)
}

/** Si el elemento es más alto que la pantalla, el recuadro se limita a la parte visible. */
function recortarAPantalla(r: DOMRect): DOMRect {
  const margen = 8
  const top = Math.max(r.top, margen)
  const bottom = Math.min(r.bottom, window.innerHeight - margen)
  return new DOMRect(r.left, top, r.width, Math.max(bottom - top, 40))
}

export function Tour({ steps, isOpen, onClose, onComplete, onIr }: TourProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  // El panel se repinta a menudo: los pasos se leen siempre de aquí para no
  // reiniciar nada cuando cambia la identidad del array.
  const stepsRef = useRef(steps)
  useEffect(() => {
    stepsRef.current = steps
  })
  const objetivosRef = useRef<HTMLElement[]>([])

  // Al llegar a un paso: ejecutar su acción, esperar al elemento, llevarlo a la
  // vista y medirlo. Si no aparece, el paso se enseña centrado y sin recuadro.
  useEffect(() => {
    if (!isOpen) return
    const paso = stepsRef.current[currentStep]
    if (!paso) return

    let cancelado = false
    let timer: ReturnType<typeof setTimeout> | undefined
    setRect(null)
    objetivosRef.current = []
    paso.action?.()

    const inicio = Date.now()
    const sondear = () => {
      if (cancelado) return
      const elementos = buscarAncla(paso.anchor)
      const esperados = Array.isArray(paso.anchor) ? paso.anchor.length : paso.anchor ? 1 : 0
      const completo = elementos.length > 0 && elementos.length >= esperados
      const agotado = Date.now() - inicio > ESPERA_MAXIMA_MS
      if (elementos.length > 0 && (completo || agotado)) {
        const alto = abarcar(elementos).height
        elementos[0].scrollIntoView({
          block: alto > window.innerHeight * 0.75 ? 'start' : 'center',
          inline: 'nearest',
        })
        objetivosRef.current = elementos
        setRect(recortarAPantalla(abarcar(elementos)))
        return
      }
      if (!paso.anchor || agotado) return
      timer = setTimeout(sondear, 80)
    }
    timer = setTimeout(sondear, 80)
    return () => {
      cancelado = true
      if (timer) clearTimeout(timer)
    }
  }, [currentStep, isOpen])

  // El recuadro sigue al elemento si se hace scroll o cambia el tamaño de la ventana.
  useEffect(() => {
    if (!isOpen) return
    const reajustar = () => {
      const vivos = objetivosRef.current.filter((e) => e.isConnected)
      if (vivos.length > 0) setRect(recortarAPantalla(abarcar(vivos)))
    }
    window.addEventListener('resize', reajustar)
    window.addEventListener('scroll', reajustar, true)
    return () => {
      window.removeEventListener('resize', reajustar)
      window.removeEventListener('scroll', reajustar, true)
    }
  }, [isOpen])

  const total = steps.length
  const paso = steps[currentStep]
  const salir = () => {
    onComplete()
    onClose()
  }
  const siguiente = () => {
    if (currentStep < total - 1) setCurrentStep(currentStep + 1)
    else salir()
  }
  const anterior = () => {
    if (currentStep > 0) setCurrentStep(currentStep - 1)
  }
  const llevarme = () => {
    if (paso?.siguiente) onIr(paso.siguiente)
  }

  useEffect(() => {
    if (!isOpen) return
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault()
        if (paso?.siguiente) llevarme()
        else siguiente()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        anterior()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        salir()
      }
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  })

  if (!isOpen || !paso) return null

  const esUltimo = currentStep === total - 1
  const esPrimero = currentStep === 0

  // Posición del texto: debajo del elemento si cabe, si no encima; sin elemento, centrado.
  let top: number
  let left: number
  if (rect) {
    left = rect.left + rect.width / 2 - ANCHO_TOOLTIP / 2
    const cabeAbajo = rect.bottom + HUECO + ALTO_TOOLTIP <= window.innerHeight
    const cabeArriba = rect.top - HUECO - ALTO_TOOLTIP >= 0
    if (cabeAbajo) top = rect.bottom + HUECO
    else if (cabeArriba) top = rect.top - HUECO - ALTO_TOOLTIP
    else top = window.innerHeight - ALTO_TOOLTIP - 16
  } else {
    left = window.innerWidth / 2 - ANCHO_TOOLTIP / 2
    top = window.innerHeight / 2 - ALTO_TOOLTIP / 2
  }
  left = Math.max(16, Math.min(left, window.innerWidth - ANCHO_TOOLTIP - 16))
  top = Math.max(16, Math.min(top, window.innerHeight - 16 - 120))

  return createPortal(
    <>
      {/* Con elemento, el propio recuadro oscurece el resto; sin él, un velo simple. */}
      {!rect && <div className="tour-velo" onClick={salir} aria-hidden="true" />}
      {rect && (
        <div
          className="tour-recuadro"
          aria-hidden="true"
          style={{
            top: rect.top - 4,
            left: rect.left - 4,
            width: rect.width + 8,
            height: rect.height + 8,
          }}
        />
      )}
      <div
        role="dialog"
        aria-label={paso.title}
        className="tour-tooltip"
        style={{ top, left, width: ANCHO_TOOLTIP }}
      >
        <div className="tour-cab">
          <div>
            <h3>{paso.title}</h3>
            <p className="tour-contador">
              Paso {currentStep + 1} de {total}
            </p>
          </div>
          <button type="button" className="tour-cerrar" onClick={salir} aria-label="Cerrar tour">
            ✕
          </button>
        </div>
        <div className="tour-texto">
          {paso.content.split('\n').map((linea, i) => (
            <p key={i}>{linea}</p>
          ))}
        </div>
        {paso.siguiente ? (
          <div className="tour-botones tour-botones-fin">
            {!esPrimero && (
              <button type="button" className="tour-sec" onClick={anterior}>
                ← Atrás
              </button>
            )}
            <button type="button" className="tour-sec" onClick={salir}>
              No, omitir
            </button>
            <button type="button" className="tour-prim" onClick={llevarme}>
              Sí, llévame
            </button>
          </div>
        ) : (
          <div className="tour-botones">
            {!esUltimo ? (
              <button type="button" className="tour-omitir" onClick={salir}>
                Omitir tour
              </button>
            ) : (
              <span />
            )}
            <div className="tour-botones-der">
              {!esPrimero && (
                <button type="button" className="tour-sec" onClick={anterior}>
                  ← Atrás
                </button>
              )}
              <button type="button" className="tour-prim" onClick={siguiente}>
                {esUltimo ? 'Finalizar' : 'Siguiente →'}
              </button>
            </div>
          </div>
        )}
      </div>
    </>,
    document.body,
  )
}
