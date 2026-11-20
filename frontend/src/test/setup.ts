import '@testing-library/jest-dom/vitest'

// jsdom no implementa scrollIntoView; la página lo llama en un setTimeout
// que puede caer tras el test y romper la ejecución (fallo intermitente).
Element.prototype.scrollIntoView = () => {}

// Vitest corre en entorno node: sin storage local los tests de cola
// fallarían antes de empezar. Polyfill mínimo solo si falta (no afecta a
// los tests reales del navegador, donde existe).
if (typeof localStorage === 'undefined') {
  const store = new Map<string, string>()
  const fake: Storage = {
    get length() {
      return store.size
    },
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v)
    },
    removeItem: (k: string) => {
      store.delete(k)
    },
    clear: () => {
      store.clear()
    },
    key: (n: number) => Array.from(store.keys())[n] ?? null,
  }
  Object.defineProperty(window, 'localStorage', { value: fake, configurable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: fake, configurable: true })
}
