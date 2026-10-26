/** "hace 5 min" a partir de un ISO; la hora sola si es de otro día. */
export function haceCuanto(iso: string, ahora = new Date()): string {
  const fecha = new Date(iso)
  const min = Math.floor((ahora.getTime() - fecha.getTime()) / 60000)
  if (min < 1) return 'ahora'
  if (min < 60) return `hace ${min} min`
  if (min < 24 * 60) return `hace ${Math.floor(min / 60)} h`
  return fecha.toLocaleString('es-ES')
}
