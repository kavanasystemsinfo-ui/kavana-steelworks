/** Vistas del panel de mando, una por pregunta y por rol que la hace. */
export type Vista = 'turno' | 'planta' | 'material' | 'costes' | 'gestion'

export const VISTAS: { valor: Vista; texto: string }[] = [
  { valor: 'turno', texto: 'Turno' },
  { valor: 'planta', texto: 'Planta' },
  { valor: 'material', texto: 'Material' },
  { valor: 'costes', texto: 'Costes' },
  { valor: 'gestion', texto: 'Gestión' },
]

/** Vista pedida en la URL (?vista=...); cualquier otro valor cae en Turno. */
export function vistaDeUrl(valor: string | null): Vista {
  return VISTAS.some((v) => v.valor === valor) ? (valor as Vista) : 'turno'
}
