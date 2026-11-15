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

    let settled = false
    const resolvePosition = ({ coords }: GeolocationPosition) => {
      if (settled) return
      settled = true
      resolve({
        latitude: coords.latitude,
        longitude: coords.longitude,
        accuracyMeters: coords.accuracy,
      })
    }
    const rejectPosition = (error: GeolocationPositionError) => {
      if (settled || error.code === error.PERMISSION_DENIED) {
        if (!settled) {
          settled = true
          reject(new Error('Location permission was denied. You can choose your area manually.'))
        }
        return
      }
      navigator.geolocation.getCurrentPosition(resolvePosition, () => {
        if (!settled) {
          settled = true
          reject(new Error('We could not get your current location. Check your device settings and try again.'))
        }
      }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 })
    }
    navigator.geolocation.getCurrentPosition(resolvePosition, rejectPosition, {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
    })
  })
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
