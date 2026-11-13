/**
 * Mock API client. Stands in for the real FastAPI backend (see architecture.md) so
 * the frontend can be built and tested before the API exists. Swap each function
 * body here for a real request once the backend contract is agreed — callers in
 * `features/*` are written against these same return shapes either way.
 */
export function delay<T>(value: T, ms = 500): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

export function fail(ms = 500): Promise<never> {
  return new Promise((_, reject) => setTimeout(reject, ms))
}
