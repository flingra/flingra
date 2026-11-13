import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNaira(amountNaira: number) {
  const sign = amountNaira < 0 ? '-' : ''
  return `${sign}₦${Math.abs(amountNaira).toLocaleString('en-NG')}`
}

/** Deterministic string hash (FNV-1a) so the same seed always maps to the same bucket. */
export function hashSeed(seed: string, bucketCount: number) {
  let hash = 0x811c9dc5
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0) % bucketCount
}
