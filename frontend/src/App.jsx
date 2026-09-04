import { useCallback, useEffect, useMemo, useState } from "react"
import { api } from "./lib/api"
import { PARAMETER_LABELS } from "./lib/bands"
import { loadSnapshot, findStation, nearestLocally } from "./lib/snapshot"
import Alerts from "./components/Alerts"
import BandLegend from "./components/BandLegend"
import Compare from "./components/Compare"
import Dashboard from "./components/Dashboard"
import MapView from "./components/MapView"
import Methodology from "./components/Methodology"
import StationPanel from "./components/StationPanel"

const SCREENS = [
  ["map", "Map"],
  ["dashboard", "Dashboard"],
  ["compare", "Compare"],
  ["alerts", "Alerts"],
  ["method", "Methodology"],
]

const MAX_KM = 50

/**
 * Which screen to open on.
 *
 * Normally the hash. But the verification and unsubscribe links in the
 * emails are PATHS -- /alerts/verify?token=... -- because a path reads
 * as a real link in a message where a bare "#alerts" does not. Those
 * paths have to land on the alerts screen, or the token is never
 * redeemed: the component that reads it is simply not mounted, and the
 * reader sees the map and assumes the link is broken.
 */
function initialScreen() {
  if (window.location.pathname.startsWith("/alerts")) return "alerts"
  return window.location.hash.replace("#", "") || "map"
}

export default function App() {
  const [snapshot, setSnapshot] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [screen, setScreen] = useState(initialScreen)
  const [selectedId, setSelectedId] = useState(null)
  const [probe, setProbe] = useState(null)
  const [probeResult, setProbeResult] = useState(null)
  const [flyTo, setFlyTo] = useState(null)
  const [sheet, setSheet] = useState("peek")

  useEffect(() => {
    loadSnapshot().then(setSnapshot).catch((e) => setLoadError(e.message))
  }, [])

  useEffect(() => {
    const onHash = () => setScreen(initialScreen())
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  const goto = useCallback((next) => {
    // Leaving a /alerts/verify path: drop the path and its token so the
    // link is not redeemed again on the next render.
    if (window.location.pathname !== "/") {
      window.history.replaceState(null, "", `/#${next}`)
    } else {
      window.location.hash = next
    }
    setScreen(next)
  }, [])

  const parameter = snapshot?.meta.parameter || "pm25"
  const station = useMemo(
    () => (snapshot && selectedId ? findStation(snapshot, selectedId) : null),
    [snapshot, selectedId])

  const onSelect = useCallback((id) => {
    setSelectedId(id)
    setProbeResult(null)
    setProbe(null)
    // Deliberately does NOT expand the sheet on selection. On a narrow
    // screen the panel overlays the map, and opening it full would hide
    // the marker the reader just tapped along with its neighbours --
    // the context that makes the number mean anything. They can drag it
    // up; the map stays visible until they ask otherwise.
    if (screen !== "map") goto("map")
  }, [screen, goto])

  /**
   * Click on empty map -> nearest station.
   *
   * Asks the API first, because that is the query the spatial index
   * exists for. If the API is down it falls back to a haversine sweep in
   * the browser over the bundled snapshot, and SAYS SO -- the feature
   * degrades rather than disappearing, and the reader is told which
   * answer they are looking at.
   */
  const onProbe = useCallback(async (lat, lon) => {
    setSelectedId(null)
    setProbe({ lat, lon, maxKm: MAX_KM, found: true })
    setProbeResult(null)
    setSheet("peek")

    const res = await api.nearest(lat, lon, MAX_KM, parameter)
    if (res.ok) {
      setProbe({ lat, lon, maxKm: MAX_KM, found: true })
      setProbeResult({ found: true, station: res.data.station, offline: false })
      setFlyTo({ lat: res.data.station.lat, lon: res.data.station.lon })
      return
    }
    if (res.offline) {
      const local = snapshot ? nearestLocally(snapshot, lat, lon, MAX_KM) : null
      setProbe({ lat, lon, maxKm: MAX_KM, found: !!local })
      setProbeResult(local
        ? { found: true, station: local, offline: true }
        : {
            found: false, offline: true,
            message: `No monitoring station within ${MAX_KM} km of ` +
                     `${lat.toFixed(4)}, ${lon.toFixed(4)}. This is a gap in ` +
                     `the network, not a reading of clean air.`,
          })
      return
    }
    // A 404 from the API is the real "nothing in range" answer, and it
    // carries the message the API wrote.
    setProbe({ lat, lon, maxKm: MAX_KM, found: false })
    setProbeResult({
      found: false, offline: false,
      message: res.data?.message || res.error,
    })
  }, [parameter, snapshot])

  if (loadError) {
    return (
      <main className="screen">
        <h1 style={{ fontSize: 32 }}>No data bundled</h1>
        <div className="notice notice-bad" style={{ marginTop: 18, maxWidth: "70ch" }}>
          {loadError}
        </div>
      </main>
    )
  }

  if (!snapshot) {
    return (
      <main className="screen">
        <div className="kicker">Loading the bundled snapshot…</div>
        <div className="skel" style={{
          height: 300, marginTop: 20, border: "1px solid var(--hair)",
        }} />
      </main>
    )
  }

  return (
    <>
      <a href="#main" className="sr-only">Skip to content</a>
      <nav className="nav" aria-label="Primary">
        <span className="nav-brand">AIRINDEX</span>
        {SCREENS.map(([id, label]) => (
          <button
            key={id}
            className="nav-link"
            aria-current={screen === id ? "page" : undefined}
            onClick={() => goto(id)}
          >
            {label}
          </button>
        ))}
        <span className="kicker num" style={{ marginLeft: 8 }}>
          {PARAMETER_LABELS[parameter]}
        </span>
      </nav>

      {snapshot.meta.provenance.synthetic && (
        <div className="provenance-banner" style={{
          padding: "8px var(--pad-x)",
          borderBottom: "1px solid var(--hair)",
          background: "rgba(201,73,124,0.10)",
          fontSize: 12, color: "var(--ink)",
        }}>
          <strong>Synthetic measurements.</strong>{" "}
          <span style={{ color: "var(--mute)" }}>
            Real station identities and coordinates; every concentration value
            is generated. Do not cite these numbers.
          </span>{" "}
          <button className="nav-link" style={{
            textTransform: "none", letterSpacing: 0, color: "var(--accent)",
          }} onClick={() => goto("method")}>
            Why
          </button>
        </div>
      )}

      <main id="main">
        {screen === "map" && (
          <div className="map-grid">
            <div className="map-wrap">
              <MapView
                stations={snapshot.stations}
                selectedId={selectedId}
                onSelect={onSelect}
                onProbe={onProbe}
                probe={probe}
                flyTo={flyTo}
              />
              <div className="map-legend">
                <BandLegend parameter={parameter} compact />
              </div>
            </div>
            <aside className="panel" data-sheet={sheet} aria-label="Station detail">
              {/* Only rendered on narrow screens, where the panel is a
                  bottom sheet over the map. .sheet-toggle is display:none
                  above the breakpoint -- an inline style could never be
                  un-hidden by the media query. */}
              <button
                className="btn sheet-toggle"
                onClick={() => setSheet((s) => (s === "full" ? "peek" : "full"))}
                aria-expanded={sheet === "full"}
              >
                {sheet === "full" ? "Collapse panel" : "Expand panel"}
              </button>
              <StationPanel
                station={station}
                snapshot={snapshot}
                parameter={parameter}
                probeResult={probeResult}
                onClearProbe={() => { setProbe(null); setProbeResult(null) }}
                onSelect={onSelect}
              />
            </aside>
          </div>
        )}

        {screen === "dashboard" && (
          <Dashboard
            snapshot={snapshot}
            parameter={parameter}
            onOpenStation={onSelect}
            onGoto={goto}
          />
        )}
        {screen === "compare" && <Compare snapshot={snapshot} parameter={parameter} />}
        {screen === "alerts" && <Alerts snapshot={snapshot} parameter={parameter} />}
        {screen === "method" && (
          <Methodology snapshot={snapshot} parameter={parameter} />
        )}
      </main>
    </>
  )
}
