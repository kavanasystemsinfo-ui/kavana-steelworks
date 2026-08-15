// Compresión de fotos de incidencias en el móvil antes de subirlas.
// Portado de kavana-manufacturing: una foto moderna (4032×3024, 8-15MB) no
// cabe en la API tal cual; se redimensiona a MAX_COMPRESSED_DIMENSION px y se
// exporta como JPEG con calidad adaptativa (baja hasta que el peso encaja).

export const MAX_COMPRESSED_BYTES = 4 * 1024 * 1024 // objetivo de peso tras comprimir
export const MAX_COMPRESSED_DIMENSION = 1600 // lado mayor en px (suficiente para evidencia)

/** Dimensiones de destino preservando el aspect ratio; sin escalado si ya caben. */
export function computeTargetSize(
  width: number,
  height: number,
  maxDim: number = MAX_COMPRESSED_DIMENSION,
): { width: number; height: number } {
  if (width <= maxDim && height <= maxDim) return { width, height }
  const scale = maxDim / Math.max(width, height)
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  }
}

/** ¿Merece la pena comprimir? Solo fotos que superen el objetivo de peso. */
export function needsCompression(
  sizeBytes: number,
  limitBytes: number = MAX_COMPRESSED_BYTES,
): boolean {
  return sizeBytes > limitBytes
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('No se pudo codificar la imagen'))),
      type,
      quality,
    )
  })
}

/**
 * Comprime una foto: la redimensiona a MAX_COMPRESSED_DIMENSION y la exporta
 * como JPEG bajando calidad hasta que pese ≤ MAX_COMPRESSED_BYTES (o hasta
 * calidad 0.4, mínimo razonable para evidencia). Devuelve un File nuevo .jpg.
 */
export async function compressImage(
  file: File,
  maxDim: number = MAX_COMPRESSED_DIMENSION,
  maxBytes: number = MAX_COMPRESSED_BYTES,
): Promise<File> {
  const bitmap = await createImageBitmap(file)
  try {
    const target = computeTargetSize(bitmap.width, bitmap.height, maxDim)
    const canvas = document.createElement('canvas')
    canvas.width = target.width
    canvas.height = target.height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas no disponible')
    ctx.drawImage(bitmap, 0, 0, target.width, target.height)

    let quality = 0.85
    let blob = await canvasToBlob(canvas, 'image/jpeg', quality)
    while (blob.size > maxBytes && quality > 0.4) {
      quality -= 0.15
      blob = await canvasToBlob(canvas, 'image/jpeg', quality)
    }

    const baseName = file.name.replace(/\.[^.]+$/, '') || 'foto'
    return new File([blob], `${baseName}.jpg`, {
      type: 'image/jpeg',
      lastModified: Date.now(),
    })
  } finally {
    bitmap.close()
  }
}
