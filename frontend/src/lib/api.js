/**
 * API client.
 *
 * The base URL comes from VITE_API_BASE. There is no hardcoded
 * localhost anywhere in src/ -- this is the only place a URL is built.
 *
 * Every call reports failure as data rather than throwing, because the
 * backend being down is a NORMAL state for this app: the map is
 * supposed to keep working. Callers get { ok, data, error, offline } and
 * decide what to degrade.
 */
const BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:5001/api")
  .replace(/\/$/, "")

async function request(path, options = {}) {
  try {
    const resp = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    })
    let body = null
    try {
      body = await resp.json()
    } catch {
      // This API returns JSON for every response, errors included. A
      // non-JSON body therefore means something OTHER than our API
      // answered on this port, which for our purposes is the same as
      // the API being down -- so it is reported as offline and callers
      // take their fallback path.
      //
      // This is not hypothetical. On macOS, Control Center's AirPlay
      // Receiver holds port 5000 and replies HTTP 403 with an HTML
      // body. Treating that as a normal error left the app showing a
      // parse failure while a perfectly good offline fallback sat
      // unused. (The default port is now 5001 for the same reason.)
      return {
        ok: false, status: resp.status, data: null, offline: true,
        error: `Something other than the API answered on ${BASE} ` +
               `(HTTP ${resp.status}, non-JSON). If this is macOS, ` +
               `port 5000 is AirPlay Receiver -- check VITE_API_BASE.`,
      }
    }
    if (!resp.ok) {
      return {
        ok: false, status: resp.status, data: body, offline: false,
        error: body?.message || `HTTP ${resp.status}`,
      }
    }
    return { ok: true, status: resp.status, data: body, error: null, offline: false }
  } catch (err) {
    // Network-level failure: Flask is not running, or CORS refused it.
    return {
      ok: false, status: 0, data: null, offline: true,
      error: "The API is not reachable. Start it with: " +
             "cd backend && .venv/bin/python wsgi.py",
    }
  }
}

export const api = {
  base: BASE,
  health: () => request("/health"),

  nearest: (lat, lon, maxKm = 50, parameter = "pm25") =>
    request(`/stations/nearest?lat=${encodeURIComponent(lat)}` +
            `&lon=${encodeURIComponent(lon)}&max_km=${maxKm}` +
            `&parameter=${parameter}`),

  cities: (parameter = "pm25") => request(`/cities?parameter=${parameter}`),

  compare: ({ cities, parameter = "pm25", from, to }) => {
    const params = new URLSearchParams({ cities: cities.join(","), parameter })
    if (from) params.set("from", from)
    if (to) params.set("to", to)
    return request(`/compare?${params}`)
  },

  series: (stationId, { parameter = "pm25", from, to } = {}) => {
    const params = new URLSearchParams({ parameter })
    if (from) params.set("from", from)
    if (to) params.set("to", to)
    return request(`/stations/${stationId}/series?${params}`)
  },

  subscribe: (payload) =>
    request("/subscriptions", { method: "POST", body: JSON.stringify(payload) }),

  verify: (token) => request(`/subscriptions/verify?token=${encodeURIComponent(token)}`),

  unsubscribe: (token) =>
    request(`/subscriptions/${encodeURIComponent(token)}`, { method: "DELETE" }),
}
