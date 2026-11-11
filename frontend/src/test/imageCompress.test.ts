import { describe, it, expect } from 'vitest'
import {
  isHeicFile,
  assertNotHeic,
  needsCompression,
  computeTargetSize,
  HEIC_EXTENSIONS,
  SUPPORTED_IMAGE_TYPES,
} from '../utils/imageCompress'

describe('imageCompress - HEIC detection', () => {
  const createFile = (name: string, type = '') =>
    new File(['dummy content'], name, { type })

  it('detects HEIC by extension .heic', () => {
    const file = createFile('IMG_1234.heic')
    expect(isHeicFile(file)).toBe(true)
  })

  it('detects HEIC by extension .heif', () => {
    const file = createFile('IMG_1234.heif')
    expect(isHeicFile(file)).toBe(true)
  })

  it('detects HEIC by MIME type image/heic', () => {
    const file = createFile('photo', 'image/heic')
    expect(isHeicFile(file)).toBe(true)
  })

  it('detects HEIC by MIME type image/heif', () => {
    const file = createFile('photo', 'image/heif')
    expect(isHeicFile(file)).toBe(true)
  })

  it('does not detect JPEG as HEIC', () => {
    const file = createFile('IMG_1234.jpg', 'image/jpeg')
    expect(isHeicFile(file)).toBe(false)
  })

  it('does not detect PNG as HEIC', () => {
    const file = createFile('IMG_1234.png', 'image/png')
    expect(isHeicFile(file)).toBe(false)
  })

  it('does not detect WebP as HEIC', () => {
    const file = createFile('IMG_1234.webp', 'image/webp')
    expect(isHeicFile(file)).toBe(false)
  })

  it('throws clear error for HEIC in assertNotHeic', () => {
    const file = createFile('IMG_1234.heic')
    expect(() => assertNotHeic(file)).toThrow(/HEIC.*iPhone/)
    expect(() => assertNotHeic(file)).toThrow(/Más compatibles/)
  })

  it('does not throw for JPEG in assertNotHeic', () => {
    const file = createFile('IMG_1234.jpg', 'image/jpeg')
    expect(() => assertNotHeic(file)).not.toThrow()
  })
})

describe('imageCompress - needsCompression', () => {
  it('returns false for file under 4MB', () => {
    expect(needsCompression(3 * 1024 * 1024)).toBe(false)
  })

  it('returns true for file over 4MB', () => {
    expect(needsCompression(5 * 1024 * 1024)).toBe(true)
  })
})

describe('imageCompress - computeTargetSize', () => {
  it('returns original size if under maxDim', () => {
    expect(computeTargetSize(800, 600)).toEqual({ width: 800, height: 600 })
  })

  it('scales down proportionally when exceeding maxDim width', () => {
    expect(computeTargetSize(3200, 2400)).toEqual({ width: 1600, height: 1200 })
  })

  it('scales down proportionally when exceeding maxDim height', () => {
    expect(computeTargetSize(1200, 3200)).toEqual({ width: 600, height: 1600 })
  })
})

describe('imageCompress - constants', () => {
  it('exports HEIC_EXTENSIONS', () => {
    expect(HEIC_EXTENSIONS).toEqual(['.heic', '.heif'])
  })

  it('exports SUPPORTED_IMAGE_TYPES matching backend magic bytes', () => {
    expect(SUPPORTED_IMAGE_TYPES).toEqual([
      'image/jpeg',
      'image/png',
      'image/webp',
      'image/gif',
    ])
  })
})

// Note: compressImage requires DOM APIs (createImageBitmap, canvas) so it's tested via
// browser automation / integration tests