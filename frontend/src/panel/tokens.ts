/** Colores del panel de mando (espejo de --color-p-* en index.css).
 *  En JSX se usan las clases de Tailwind (bg-p-ok-bg, text-p-mal...); estos
 *  valores son para los SVG y los estilos que no pasan por Tailwind.
 */
export const COLORES = {
  fondo: '#F4F5F7',
  tarjeta: '#FFFFFF',
  borde: '#E3E6EA',
  linea: '#EEF0F3',
  texto: '#14181F',
  texto2: '#4A5361',
  etiqueta: '#5F6876',
  plan: '#2456C9',
  prevision: '#8A93A0',
  ok: '#157F3D',
  aviso: '#A15C07',
  mal: '#B42318',
  gris: '#4A5361',
} as const

/** Modo TV (oscuro, para leer a varios metros). */
export const COLORES_TV = {
  fondo: '#0B0E12',
  tarjeta: '#161B22',
  texto: '#F2F4F7',
  texto2: '#A9B1BC',
  ok: { bg: '#0F2A1C', borde: '#1F6B43', fg: '#5BD68F' },
  mal: { bg: '#3A1210', borde: '#C2412F', fg: '#FF8A80' },
  aviso: { bg: '#33240A', borde: '#B57A12', fg: '#F5B544' },
  gris: { bg: '#161B22', borde: '#2C333D', fg: '#A9B1BC' },
} as const

/** Estado de un dato: el color nunca va solo, siempre con su texto. */
export type Tono = 'ok' | 'aviso' | 'mal' | 'gris'

/** Clases de Tailwind por tono (literales completos para que Tailwind los detecte). */
export const CLASES_TONO: Record<Tono, { texto: string; fondo: string; borde: string; solido: string }> = {
  ok: { texto: 'text-p-ok', fondo: 'bg-p-ok-bg', borde: 'border-p-ok-borde', solido: 'bg-p-ok' },
  aviso: {
    texto: 'text-p-aviso',
    fondo: 'bg-p-aviso-bg',
    borde: 'border-p-aviso-borde',
    solido: 'bg-p-aviso',
  },
  mal: { texto: 'text-p-mal', fondo: 'bg-p-mal-bg', borde: 'border-p-mal-borde', solido: 'bg-p-mal' },
  gris: {
    texto: 'text-p-gris',
    fondo: 'bg-p-gris-bg',
    borde: 'border-p-gris-borde',
    solido: 'bg-p-gris',
  },
}
