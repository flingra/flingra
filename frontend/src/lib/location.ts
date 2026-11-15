export interface CurrentLocation {
  latitude: number
  longitude: number
  accuracyMeters: number
}

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined

interface GoogleGeocodeResponse {
  status: string
  results: Array<{
    address_components: Array<{ long_name: string; types: string[] }>
  }>
}

export function getCurrentLocation(): Promise<CurrentLocation> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Your browser does not support location access.'))
      return
    }

    navigator.geolocation.getCurrentPosition(
      ({ coords }) =>
        resolve({
          latitude: coords.latitude,
          longitude: coords.longitude,
          accuracyMeters: coords.accuracy,
        }),
      (error) => {
        const message =
          error.code === error.PERMISSION_DENIED
            ? 'Location permission was denied. You can choose your area manually.'
            : 'We could not get your current location. Check your device settings and try again.'
        reject(new Error(message))
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    )
  })
}

export async function getApproximateArea(location: CurrentLocation): Promise<string | null> {
  if (!GOOGLE_MAPS_API_KEY) return null

  const params = new URLSearchParams({
    latlng: `${location.latitude},${location.longitude}`,
    key: GOOGLE_MAPS_API_KEY,
  })
  try {
    const response = await fetch(`https://maps.googleapis.com/maps/api/geocode/json?${params}`)
    if (!response.ok) return null

    const result = (await response.json()) as GoogleGeocodeResponse
    if (result.status !== 'OK' || result.results.length === 0) return null

    const components = result.results[0].address_components
    const area =
      components.find((component) => component.types.includes('sublocality_level_1')) ??
      components.find((component) => component.types.includes('sublocality')) ??
      components.find((component) => component.types.includes('locality'))
    const city = components.find((component) => component.types.includes('administrative_area_level_2'))
    const state = components.find((component) => component.types.includes('administrative_area_level_1'))
    if (!area) return null

    const suffix = city && city.long_name !== area.long_name ? city.long_name : state?.long_name
    return suffix && suffix !== area.long_name ? `${area.long_name}, ${suffix}` : area.long_name
  } catch {
    return null
  }
}
