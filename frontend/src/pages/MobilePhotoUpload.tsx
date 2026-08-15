import { useState } from 'react'
import { compressImage, needsCompression } from '../utils/imageCompress'

interface Props {
  sessionId: string
}

type PageStatus = 'idle' | 'uploading' | 'success' | 'error'

/**
 * Página pública /mobile-upload/:sessionId — la abre el operario escaneando el
 * QR del modal de incidencias. Sube UNA foto como evidencia; el sessionId actúa
 * como credencial de un solo uso (caduca en 15 min, valida magic bytes y 10MB).
 * Portado de kavana-manufacturing; las fotos se comprimen en el móvil antes de
 * subir para que el tamaño de la cámara no rompa el límite.
 */
export function MobilePhotoUpload({ sessionId }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [status, setStatus] = useState<PageStatus>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [optimized, setOptimized] = useState(false)

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (!selected) return
    try {
      const finalFile = needsCompression(selected.size)
        ? await compressImage(selected)
        : selected
      setOptimized(finalFile !== selected)
      setFile(finalFile)
      setPreview(URL.createObjectURL(finalFile))
      setStatus('idle')
      setErrorMessage('')
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : 'No se pudo procesar la imagen. Inténtalo de nuevo.',
      )
      setStatus('error')
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setStatus('uploading')
    setErrorMessage('')
    try {
      const form = new FormData()
      form.append('foto', file)
      const res = await fetch(`/api/v1/incidencias/upload-mobile/${sessionId}`, {
        method: 'POST',
        body: form,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al subir la foto')
      }
      setStatus('success')
    } catch (e) {
      setStatus('error')
      setErrorMessage(
        e instanceof Error ? e.message : 'Error al conectar con el servidor. Inténtalo de nuevo.',
      )
    }
  }

  if (status === 'success') {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center bg-kavana-dark p-6 text-center text-slate-100">
        <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full border-2 border-kavana-ok/60 bg-kavana-ok/10">
          <span className="text-4xl">✓</span>
        </div>
        <h1 className="text-3xl font-black uppercase tracking-tight">¡Foto enviada!</h1>
        <p className="mt-3 max-w-xs text-sm text-kavana-text-dim">
          La imagen ya aparece en el panel del puesto de trabajo.
        </p>
        {preview && (
          <img
            src={preview}
            alt="Foto enviada"
            className="mt-8 max-h-56 w-full max-w-xs rounded-sm border-2 border-kavana-border object-cover"
          />
        )}
        <button
          onClick={() => window.close()}
          className="mt-8 rounded-sm bg-kavana-orange px-6 py-3 text-sm font-black uppercase tracking-wider text-black hover:opacity-90"
        >
          Cerrar ventana
        </button>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen flex-col bg-kavana-dark text-slate-100">
      <div className="p-6 pb-2">
        <p className="text-[10px] font-black uppercase tracking-[0.3em] text-kavana-orange">
          KAVANA Steelworks
        </p>
        <h1 className="mt-1 text-2xl font-black uppercase tracking-tight">Adjuntar evidencia</h1>
        <p className="mt-2 text-[10px] font-bold uppercase tracking-widest text-kavana-text-dim">
          Sesión:{' '}
          <span className="rounded bg-kavana-surface px-2 py-0.5 font-mono">
            {sessionId.slice(0, 8)}
          </span>
        </p>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-6 p-6">
        {status === 'error' && (
          <div className="w-full max-w-sm rounded-sm border border-kavana-danger/50 bg-kavana-danger/10 p-4 text-sm">
            <p className="font-black uppercase tracking-wider">Error</p>
            <p className="mt-1">{errorMessage}</p>
          </div>
        )}

        {!preview ? (
          <label className="flex aspect-square w-full max-w-sm cursor-pointer flex-col items-center justify-center gap-6 rounded-sm border-4 border-dashed border-kavana-border transition hover:border-kavana-orange/60 hover:bg-kavana-surface/40">
            <div className="flex h-24 w-24 items-center justify-center rounded-full border-2 border-kavana-orange bg-kavana-surface">
              <span className="text-4xl">📷</span>
            </div>
            <div className="text-center">
              <p className="text-lg font-black uppercase tracking-wide">Tomar foto</p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-kavana-text-dim">
                Suelo de fábrica
              </p>
            </div>
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={handleFileChange}
            />
          </label>
        ) : (
          <div className="relative w-full max-w-sm overflow-hidden rounded-sm border-4 border-kavana-border">
            <img src={preview} alt="Vista previa" className="aspect-square w-full object-cover" />
            {optimized && (
              <div className="absolute bottom-4 left-4 rounded-sm bg-black/60 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-kavana-ok">
                Foto optimizada
              </div>
            )}
            <button
              onClick={() => {
                setFile(null)
                setPreview('')
                setOptimized(false)
              }}
              className="absolute right-4 top-4 rounded-full bg-black/60 p-2.5 text-white hover:bg-kavana-danger"
              aria-label="Quitar foto"
            >
              ✕
            </button>
          </div>
        )}

        {file && (
          <button
            onClick={handleUpload}
            disabled={status === 'uploading'}
            className="w-full max-w-sm rounded-sm bg-kavana-orange px-6 py-4 text-base font-black uppercase tracking-wider text-black hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
          >
            {status === 'uploading' ? 'Enviando…' : 'Enviar al PC'}
          </button>
        )}
      </div>

      <div className="p-8 text-center">
        <p className="text-[10px] font-black tracking-[0.3em] text-kavana-text-dim uppercase">
          Kavana Systems · Industrial MES
        </p>
      </div>
    </main>
  )
}
