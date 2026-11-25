import { apiRequest } from './api/client'

export interface CurrentLocation {
  latitude: number
  longitude: number
  accuracyMeters: number
}

export function getCurrentLocation(): Promise<CurrentLocation> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Your browser does not support location access.'))
      return
    }

    let attempts = 0
    const requestPosition = () => {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          resolve({
            latitude: coords.latitude,
            longitude: coords.longitude,
            accuracyMeters: coords.accuracy,
          })
        },
        (error) => {
          if (error.code === error.PERMISSION_DENIED) {
            reject(new Error('Location access is blocked. You can choose your area manually.'))
            return
          }
          if (attempts === 0) {
            attempts += 1
            window.setTimeout(requestPosition, 500)
            return
          }
          reject(new Error('We could not get a fresh location fix. You can choose your area manually.'))
        },
        { enableHighAccuracy: true, timeout: attempts === 0 ? 15000 : 10000, maximumAge: 0 },
      )
    }

    requestPosition()
  })
}

export interface LocationSearchResult {
  name: string
  area: string
  latitude: number
  longitude: number
}

export async function searchLocations(query: string): Promise<LocationSearchResult[]> {
  const result = await apiRequest<{ results: LocationSearchResult[] }>(
    `/location/search?q=${encodeURIComponent(query.trim())}`,
  )
  return result.results
}

export async function getApproximateArea(location: CurrentLocation): Promise<string | null> {
  try {
    const result = await apiRequest<{ area: string | null }>(
      `/location/reverse?latitude=${encodeURIComponent(location.latitude)}&longitude=${encodeURIComponent(location.longitude)}`,
    )
    return result.area
  } catch {
    return null
  }
}
