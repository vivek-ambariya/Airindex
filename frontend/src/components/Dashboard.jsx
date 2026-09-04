import { useMemo } from "react"
import { PARAMETER_LABELS, UNITS, bandColourFor } from "../lib/bands"
import { fmtDate, fmtInt, fmtNum, fmtPct } from "../lib/format"
import BandChip from "./BandChip"
import BandLegend from "./BandLegend"
import Blueprint from "./Blueprint"
import Sparkline from "./Sparkline"
import Unit from "./Unit"

function Stat({ value, label, note, colour }) {
  return (
    <Blueprint className="stat">
      <div className="stat-v num" style={colour ? { color: colour } : undefined}>{value}</div>
      <div className="kicker stat-l">{label}</div>
      {note && (
        <div style={{ fontSize: 12, color: "var(--mute-2)", marginTop: 6 }}>{note}</div>
      )}
    </Blueprint>
  )
}

/** National monthly trend, 61 months of it. */
function NationalTrend({ series, parameter }) {
  if (!series?.length) return null
  const W = 900, H = 170, PAD = { t: 12, r: 8, b: 26, l: 34 }
  const max = Math.max(...series.map((d) => d.value)) * 1.1
  const innerW = W - PAD.l - PAD.r, innerH = H - PAD.t - PAD.b
  const slot = innerW / series.length
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`National monthly mean ${parameter} across ${series.length} months`}>
        <line x1={PAD.l} x2={W - PAD.r} y1={PAD.t + innerH} y2={PAD.t + innerH}
              className="grid-line" />
        <text x={PAD.l - 4} y={PAD.t + 8} className="axis-label" textAnchor="end">
          {Math.round(max)}
        </text>
        {series.map((d, i) => {
          const h = (d.value / max) * innerH
          const isJan = d.month.endsWith("-01")
          return (
            <g key={d.month}>
              <rect x={PAD.l + slot * i + slot * 0.15} y={PAD.t + innerH - h}
                    width={slot * 0.7} height={Math.max(h, 1)}
                    fill={bandColourFor(parameter, d.value)}
                    fillOpacity="0.9">
                <title>{`${d.month}: ${fmtNum(d.value)} ${UNITS[parameter]} · ${d.n_stations} stations`}</title>
              </rect>
              {isJan && (
                <text x={PAD.l + slot * i + slot / 2} y={H - 8}
                      className="axis-label" textAnchor="middle">
                  {d.month.slice(0, 4)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      <p className="kicker" style={{ marginTop: 8, textTransform: "none", letterSpacing: 0 }}>
        Mean across reporting stations, unweighted. This leans towards wherever
        the network is dense, which is the northern plain — it is an average of
        monitors, not of people.
      </p>
    </div>
  )
}

export default function Dashboard({ snapshot, parameter, onOpenStation, onGoto }) {
  const meta = snapshot.meta

  const stats = useMemo(() => {
    const banded = snapshot.stations.filter((s) => s.band)
    const silent = snapshot.stations.filter((s) => s.silent)
    const lowComp = snapshot.stations.filter(
      (s) => !s.silent && s.completeness_30d < 50)
    const values = banded.map((s) => s.latest_value).filter((v) => v != null)
    return {
      nStations: snapshot.stations.length,
      nCities: snapshot.cities.length,
      reporting: banded.length,
      silent: silent.length,
      lowComp: lowComp.length,
      mean: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null,
      nPoints: meta.n_points,
    }
  }, [snapshot, meta])

  // Per-city sparkline: mean of that city's stations, monthly.
  const citySeries = useMemo(() => {
    const map = new Map()
    for (const s of snapshot.stations) {
      if (!s.city) continue
      if (!map.has(s.city)) map.set(s.city, [])
      map.get(s.city).push(s)
    }
    const out = new Map()
    for (const [city, list] of map) {
      const n = list[0].values.length
      const series = new Array(n).fill(null)
      for (let i = 0; i < n; i += 1) {
        let sum = 0, count = 0
        for (const s of list) {
          if (s.values[i] != null) { sum += s.values[i]; count += 1 }
        }
        if (count) series[i] = sum / count
      }
      out.set(city, series)
    }
    return out
  }, [snapshot])

  return (
    <div className="screen">
      <div className="screen-head">
        <div className="kicker">
          {meta.country === "IN" ? "India" : meta.country} · daily averages ·{" "}
          <Unit>{UNITS[parameter]}</Unit>
        </div>
        <h1 style={{ marginTop: 10 }}>Dashboard</h1>
        <p>
          {fmtInt(stats.nPoints)} daily values from {stats.nStations} stations
          across {stats.nCities} cities, {fmtDate(meta.start)} to{" "}
          {fmtDate(meta.end)}. Everything is a 24-hour mean in{" "}
          {UNITS[parameter]} — not an index number.
        </p>
      </div>

      <div className="grid" style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
      }}>
        <Stat value={fmtInt(stats.nStations)} label="Stations"
              note={`${stats.nCities} cities`} />
        <Stat value={fmtInt(stats.reporting)} label="With a band"
              note="enough data to colour" />
        <Stat value={fmtInt(stats.silent)} label="Gone silent"
              colour={stats.silent ? "var(--b5)" : undefined}
              note="no reports in 30 days" />
        <Stat value={fmtInt(stats.lowComp)} label="Under 50% complete"
              colour={stats.lowComp ? "var(--b3)" : undefined}
              note="reporting, but sparsely" />
        <Stat value={fmtNum(stats.mean)} label={`Mean ${PARAMETER_LABELS[parameter]}`}
              note="across banded stations" />
      </div>

      <div style={{ marginTop: 40 }}>
        <BandLegend parameter={parameter} />
      </div>

      <hr className="hr" />

      <h2 style={{ fontSize: 26, marginBottom: 16 }}>National monthly trend</h2>
      <NationalTrend series={snapshot.national_monthly} parameter={parameter} />

      <hr className="hr" />

      <div style={{
        display: "flex", alignItems: "baseline", justifyContent: "space-between",
        gap: 12, flexWrap: "wrap", marginBottom: 14,
      }}>
        <h2 style={{ fontSize: 26 }}>Cities by mean</h2>
        <button className="btn" onClick={() => onGoto("compare")}>
          Compare cities
        </button>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 44 }}>#</th>
              <th>City</th>
              <th className="r">Mean</th>
              <th>Band</th>
              <th style={{ width: 160 }}>Five-year trend</th>
              <th className="r">Stations</th>
              <th className="r">Complete</th>
            </tr>
          </thead>
          <tbody>
            {snapshot.cities.map((c, i) => (
              <tr key={c.city}>
                <td className="num" style={{ color: "var(--mute)" }}>{i + 1}</td>
                <td>
                  <span style={{
                    fontFamily: "var(--font-head)", fontWeight: 600,
                    textTransform: "uppercase", fontSize: 19,
                    color: c.band ? "var(--ink)" : "var(--mute)",
                  }}>
                    {c.city}
                  </span>
                  {c.state && (
                    <span style={{ color: "var(--mute-2)", fontSize: 12, marginLeft: 8 }}>
                      {c.state}
                    </span>
                  )}
                </td>
                <td className="r" style={{ fontSize: 16 }}>
                  {fmtNum(c.mean_value)}
                  <span style={{ color: "var(--mute)", fontSize: 11 }}>
                    {" "}{UNITS[parameter]}
                  </span>
                </td>
                <td><BandChip band={c.band} withheld={c.band_withheld} /></td>
                <td>
                  <Sparkline
                    values={citySeries.get(c.city) || []}
                    colour={c.band ? bandColourFor(parameter, c.mean_value) : "var(--bx)"}
                  />
                </td>
                <td className="r" style={{ color: "var(--mute)" }}>{c.n_stations}</td>
                <td className="r" style={{
                  color: c.mean_completeness < 50 ? "var(--b5)" : "var(--mute)",
                }}>
                  {fmtPct(c.mean_completeness)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
