import '@testing-library/jest-dom/vitest'

// jsdom no implementa scrollIntoView; la página lo llama en un setTimeout
// que puede caer tras el test y romper la ejecución (fallo intermitente).
Element.prototype.scrollIntoView = () => {}
