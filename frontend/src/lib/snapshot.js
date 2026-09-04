/**
 * The bundled snapshot.
 *
 * This is the map's entire data source. It is a static file written by
 * backend/jobs/publish.py and served from public/, so the map draws with
 * Flask stopped. The API is only for the things that genuinely need a
 * live query: nearest-station lookup, city comparison, and alerts.
 */
let cache = null

export async function loadSnapshot() {
  if (cache) return cache
  const resp = await fetch(`${import.meta.env.BASE_URL}snapshot.json`)
  if (!resp.ok) {
    throw new Error(
      `Could not load snapshot.json (HTTP ${resp.status}). ` +
      `Run: cd backend && .venv/bin/python -m jobs.publish`
    )
  }
  cache = await resp.json()
  return cache
}

/** Stations grouped by city, ordered by mean value descending. */
export function stationsByCity(snapshot) {
  const map = new Map()
  for (const s of snapshot.stations) {
    const key = s.city || "Unknown"
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(s)
  }
  return map
}

export function findStation(snapshot, id) {
  return snapshot.stations.find((s) => s.id === Number(id)) || null
}

/**
 * Straight-line distance in km. Used ONLY as a client-side fallback for
 * nearest-station when the API is unreachable, so that feature degrades
 * instead of disappearing.
 *
 * Note this is the same haversine the backend's test asserts against,
 * and it takes (lat, lon) in that order -- the axis-order question does
 * not arise in JS because there is no geometry type to get wrong.
 */
export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371
  const toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

export function nearestLocally(snapshot, lat, lon, maxKm = 50) {
  let best = null
  for (const s of snapshot.stations) {
    const km = haversineKm(lat, lon, s.lat, s.lon)
    if (km <= maxKm && (best === null || km < best.distance_km)) {
      best = { ...s, distance_km: Math.round(km * 1000) / 1000 }
    }
  }
  return best
}
