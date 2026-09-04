import { useEffect, useRef } from "react"
import { MapContainer, TileLayer, useMap, useMapEvents, Circle } from "react-leaflet"
import L from "leaflet"
import "leaflet.markercluster"
import { BAND_COLOURS, BAND_NAMES, NO_BAND_COLOUR, stationColour } from "../lib/bands"

// India, with enough margin for the Andamans and Kashmir.
const INDIA_CENTRE = [22.8, 80.0]
const INDIA_BOUNDS = L.latLngBounds([6.0, 67.0], [37.5, 97.5])

/**
 * Belt and braces for the marker-versus-map click problem.
 *
 * stopPropagation on the marker is the actual fix. This timestamp is a
 * second line of defence, because the failure it guards against is
 * silent and user-visible: a marker click that gets converted into a
 * "nearest station" probe looks like a dead marker, and Leaflet's
 * propagation behaviour here has changed between versions before.
 */
let suppressUntil = 0
const SUPPRESS_MS = 250
const markSuppressed = () => { suppressUntil = Date.now() + SUPPRESS_MS }
const isSuppressed = () => Date.now() < suppressUntil

/**
 * Marker cluster layer.
 *
 * leaflet.markercluster is driven directly rather than through a
 * wrapper package: the wrappers track react-leaflet's major versions
 * loosely, and this is about thirty lines of imperative Leaflet either
 * way. useMap() is the only React-Leaflet API needed.
 */
function ClusterLayer({ stations, selectedId, onSelect }) {
  const map = useMap()
  const groupRef = useRef(null)

  useEffect(() => {
    const group = L.markerClusterGroup({
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      disableClusteringAtZoom: 9,
      maxClusterRadius: 46,
      // A cluster is coloured by the WORST band it contains, not the
      // mean. Averaging hides the station that is actually in trouble,
      // which is the one a reader is looking for. Clusters containing
      // any unbanded station are marked, because "we do not know" must
      // not be averaged away either.
      iconCreateFunction: (cluster) => {
        const children = cluster.getAllChildMarkers()
        let worst = -1
        let anyUnbanded = false
        for (const m of children) {
          const band = m.options.stationBand
          if (!band) { anyUnbanded = true; continue }
          worst = Math.max(worst, BAND_NAMES.indexOf(band))
        }
        const colour = worst >= 0 ? BAND_COLOURS[worst] : NO_BAND_COLOUR
        const n = children.length
        const size = n < 5 ? 28 : n < 15 ? 34 : 42
        return L.divIcon({
          className: "",
          iconSize: [size, size],
          html:
            `<div class="cluster-dot" style="width:${size}px;height:${size}px;` +
            `background:${colour}2e;border:1px solid ${colour};` +
            `${anyUnbanded ? "border-style:dashed;" : ""}">${n}</div>`,
        })
      },
    })

    for (const s of stations) {
      const colour = stationColour(s)
      const selected = s.id === selectedId
      const r = selected ? 9 : 7
      const marker = L.marker([s.lat, s.lon], {
        stationBand: s.band,
        keyboard: true,
        title: `${s.name}${s.city ? `, ${s.city}` : ""}`,
        // Focusable and named, so the map is not pointer-only.
        alt: `${s.name}. ${s.band || s.band_withheld || "no band"}`,
        icon: L.divIcon({
          className: "",
          iconSize: [r * 2, r * 2],
          iconAnchor: [r, r],
          html:
            `<div class="marker-dot" style="width:${r * 2}px;height:${r * 2}px;` +
            `background:${colour};` +
            (s.band ? "" : "background-image:repeating-linear-gradient(45deg,#4a4a4a 0 2px,#2b2b2b 2px 4px);") +
            (selected ? "box-shadow:0 0 0 2px #749dc4,0 0 0 4px rgba(10,10,10,.9);" : "") +
            `"></div>`,
        }),
      })
      // stopPropagation matters here. Leaflet forwards a marker click on
      // to the map's own click handler, which in this app means
      // "nearest station to this point" -- so selecting a station fired
      // the probe a moment later and wiped the selection. From the
      // outside it looked like clicking a marker did nothing.
      marker.on("click", (e) => {
        L.DomEvent.stopPropagation(e)
        markSuppressed()
        onSelect(s.id)
      })
      marker.on("keypress", (e) => {
        if (e.originalEvent?.key === "Enter") {
          L.DomEvent.stopPropagation(e)
          markSuppressed()
          onSelect(s.id)
        }
      })
      group.addLayer(marker)
    }

    // Expanding a cluster is navigation, not a location question.
    group.on("clusterclick", () => markSuppressed())

    group.addTo(map)
    groupRef.current = group
    return () => {
      group.clearLayers()
      map.removeLayer(group)
    }
  }, [map, stations, selectedId, onSelect])

  return null
}

/** Turns a click on EMPTY map into a nearest-station lookup. */
function ClickProbe({ onProbe }) {
  useMapEvents({
    click(e) {
      // A click that came from a marker or a cluster is a selection,
      // not a "what is near here" question.
      if (isSuppressed()) return
      onProbe(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

function FlyTo({ target }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lon], Math.max(map.getZoom(), 9), {
      duration: 0.7,
    })
  }, [map, target])
  return null
}

export default function MapView({
  stations, selectedId, onSelect, onProbe, probe, flyTo,
}) {
  return (
    <MapContainer
      center={INDIA_CENTRE}
      zoom={5}
      minZoom={4}
      maxZoom={14}
      maxBounds={INDIA_BOUNDS.pad(0.25)}
      zoomControl
      attributionControl
      preferCanvas
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        maxZoom={19}
        detectRetina
      />
      <ClickProbe onProbe={onProbe} />
      <FlyTo target={flyTo} />

      {/* The search radius, drawn where the reader clicked. When the
          lookup fails this circle is the explanation: it shows how far
          was searched and that nothing was inside it. */}
      {probe && (
        <>
          <Circle
            center={[probe.lat, probe.lon]}
            radius={probe.maxKm * 1000}
            pathOptions={{
              color: probe.found ? "#749dc4" : "#c9497c",
              weight: 1,
              dashArray: "4 4",
              fillOpacity: 0.04,
            }}
          />
          <Circle
            center={[probe.lat, probe.lon]}
            radius={600}
            pathOptions={{
              color: "#f2f0ec", weight: 1, fillColor: "#f2f0ec", fillOpacity: 0.9,
            }}
          />
        </>
      )}

      <ClusterLayer stations={stations} selectedId={selectedId} onSelect={onSelect} />
    </MapContainer>
  )
}
