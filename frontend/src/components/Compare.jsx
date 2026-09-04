import { useEffect, useMemo, useState } from "react"
import { api } from "../lib/api"
import { PARAMETER_LABELS, UNITS } from "../lib/bands"
import { lttb } from "../lib/downsample"
import { dateAt, fmtDate, fmtNum, fmtPct } from "../lib/format"
import BandChip from "./BandChip"
import Blueprint from "./Blueprint"
import Unit from "./Unit"

const MAX_CITIES = 5
const MIN_CITIES = 2

/**
 * Cities are distinguished by DASH PATTERN as well as hue.
 *
 * Five lines separated only by colour is unreadable to roughly one man
 * in twelve, and unreadable to anyone printing it. The pattern carries
 * the identity; colour only reinforces it. Each line is also labelled
 * directly at its right-hand end, so the legend is not the only key.
 */
const SERIES_STYLE = [
  { colour: "#749dc4", dash: "" },
  { colour: "#e6c351", dash: "6 3" },
  { colour: "#4fa79a", dash: "2 3" },
  { colour: "#e08a3c", dash: "9 3 2 3" },
  { colour: "#c9497c", dash: "1 4" },
]

const RANGES = [
  { label: "1 year", days: 365 },
  { label: "3 years", days: 1095 },
  { label: "5 years", days: 1826 },
]

function CompareChart({ data, parameter }) {
  const W = 940, H = 300, PAD = { t: 14, r: 96, b: 26, l: 40 }
  const found = data.cities.filter((c) => c.found)
  if (!found.length) return null

  const all = found.flatMap((c) => c.values).filter((v) => v != null)
  const max = Math.max(...all) * 1.1
  const innerW = W - PAD.l - PAD.r, innerH = H - PAD.t - PAD.b
  const x = (i) => PAD.l + (i / Math.max(data.n_days - 1, 1)) * innerW
  const y = (v) => PAD.t + innerH - (v / max) * innerH

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`${PARAMETER_LABELS[parameter]} compared across ${found.map((c) => c.city).join(", ")}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.l} x2={W - PAD.r} y1={PAD.t + innerH * (1 - f)}
                  y2={PAD.t + innerH * (1 - f)} className="grid-line"
                  strokeOpacity={f === 0 ? 1 : 0.5} />
            <text x={PAD.l - 5} y={PAD.t + innerH * (1 - f) + 3}
                  className="axis-label" textAnchor="end">
              {Math.round(max * f)}
            </text>
          </g>
        ))}

        {(() => {
          // Direct labels are placed at each line's last real value, then
          // pushed apart so they stay readable. Cities converge in the
          // clean months, which stacked three labels on top of each
          // other -- the direct label is the primary key to the chart
          // (colour is only a reinforcement), so an unreadable one loses
          // the whole point.
          const labels = found.map((c, ci) => {
            let lastIdx = -1
            for (let i = c.values.length - 1; i >= 0; i -= 1) {
              if (c.values[i] != null) { lastIdx = i; break }
            }
            return {
              city: c.city,
              colour: SERIES_STYLE[ci % SERIES_STYLE.length].colour,
              yWanted: lastIdx >= 0 ? y(c.values[lastIdx]) : null,
            }
          }).filter((l) => l.yWanted != null)

          const GAP = 14
          labels.sort((a, b) => a.yWanted - b.yWanted)
          let prev = -Infinity
          for (const l of labels) {
            l.y = Math.max(l.yWanted, prev + GAP)
            prev = l.y
          }
          // If the stack overflowed the plot, slide the whole run up.
          const overflow = labels.length
            ? labels[labels.length - 1].y - (PAD.t + innerH)
            : 0
          if (overflow > 0) for (const l of labels) l.y -= overflow

          const placed = new Map(labels.map((l) => [l.city, l]))

          return found.map((c, ci) => {
            const style = SERIES_STYLE[ci % SERIES_STYLE.length]
            const points = lttb(c.values, 460)
            let d = "", pen = false
            for (const p of points) {
              if (p === null) { pen = false; continue }
              d += `${pen ? "L" : "M"}${x(p.i).toFixed(1)} ${y(p.v).toFixed(1)}`
              pen = true
            }
            const label = placed.get(c.city)
            return (
              <g key={c.city}>
                <path d={d} fill="none" stroke={style.colour} strokeWidth="1.4"
                      strokeDasharray={style.dash} strokeLinejoin="round" />
                {label && (
                  <>
                    {/* Leader line, for when the label had to move. */}
                    {Math.abs(label.y - label.yWanted) > 2 && (
                      <line
                        x1={W - PAD.r} y1={label.yWanted}
                        x2={W - PAD.r + 6} y2={label.y - 4}
                        stroke={style.colour} strokeWidth="0.75"
                        strokeOpacity="0.6"
                      />
                    )}
                    <text x={W - PAD.r + 8} y={label.y}
                          style={{
                            fontSize: 11, fill: style.colour,
                            fontFamily: "var(--font-body)",
                          }}>
                      {c.city}
                    </text>
                  </>
                )}
              </g>
            )
          })
        })()}

        <text x={PAD.l} y={H - 8} className="axis-label">{fmtDate(data.start)}</text>
        <text x={W - PAD.r} y={H - 8} className="axis-label" textAnchor="end">
          {fmtDate(data.end)}
        </text>
      </svg>

      <div style={{
        display: "flex", flexWrap: "wrap", gap: "8px 20px", marginTop: 12,
        paddingTop: 12, borderTop: "1px solid var(--hair)",
      }}>
        {found.map((c, ci) => {
          const style = SERIES_STYLE[ci % SERIES_STYLE.length]
          return (
            <span key={c.city} className="chip">
              <svg width="26" height="8" aria-hidden="true">
                <line x1="0" y1="4" x2="26" y2="4" stroke={style.colour}
                      strokeWidth="1.6" strokeDasharray={style.dash} />
              </svg>
              <span>{c.city}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}

export default function Compare({ snapshot, parameter }) {
  const available = useMemo(
    () => snapshot.cities.map((c) => c.city), [snapshot])

  const [selected, setSelected] = useState(() =>
    ["Delhi", "Mumbai", "Bengaluru"].filter((c) => available.includes(c))
      .slice(0, 3))
  const [rangeDays, setRangeDays] = useState(365)
  const [state, setState] = useState({ loading: false, data: null, error: null, offline: false })

  useEffect(() => {
    if (selected.length < MIN_CITIES) {
      setState({ loading: false, data: null, error: null, offline: false })
      return
    }
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    const to = snapshot.meta.end
    const from = dateAt(to, -(rangeDays - 1))
    api.compare({ cities: selected, parameter, from, to }).then((res) => {
      if (cancelled) return
      setState({
        loading: false,
        data: res.ok ? res.data : null,
        error: res.ok ? null : res.error,
        offline: res.offline,
      })
    })
    return () => { cancelled = true }
  }, [selected, parameter, rangeDays, snapshot])

  const toggle = (city) => {
    setSelected((cur) => {
      if (cur.includes(city)) return cur.filter((c) => c !== city)
      if (cur.length >= MAX_CITIES) return cur
      return [...cur, city]
    })
  }

  return (
    <div className="screen">
      <div className="screen-head">
        <div className="kicker">
          {MIN_CITIES}–{MAX_CITIES} cities · {PARAMETER_LABELS[parameter]} ·{" "}
          <Unit>{UNITS[parameter]}</Unit>
        </div>
        <h1 style={{ marginTop: 10 }}>Compare</h1>
        <p>
          A city value is the unweighted mean of its stations for that day.
          Stations under 50% completeness are left out of it entirely rather
          than dragged in at a reduced weight.
        </p>
      </div>

      <Blueprint style={{ padding: 18, marginBottom: 26 }}>
        <div style={{
          display: "flex", justifyContent: "space-between",
          alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 12,
        }}>
          <div className="kicker">
            Cities — {selected.length} of {MAX_CITIES} selected
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {RANGES.map((r) => (
              <button key={r.label} className="btn"
                      style={{ padding: "5px 10px", fontSize: 11 }}
                      aria-pressed={rangeDays === r.days}
                      onClick={() => setRangeDays(r.days)}>
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {available.map((city) => {
            const on = selected.includes(city)
            const full = !on && selected.length >= MAX_CITIES
            return (
              <button
                key={city}
                className="btn"
                style={{ padding: "6px 11px", fontSize: 12, textTransform: "none" }}
                aria-pressed={on}
                disabled={full}
                title={full ? `Remove one first — the maximum is ${MAX_CITIES}` : undefined}
                onClick={() => toggle(city)}
              >
                {city}
              </button>
            )
          })}
        </div>

        {selected.length < MIN_CITIES && (
          <p style={{ marginTop: 12, marginBottom: 0, fontSize: 13, color: "var(--b3)" }}>
            Pick at least {MIN_CITIES} cities to compare.
          </p>
        )}
      </Blueprint>

      {state.offline && (
        <div className="notice notice-warn" style={{ marginBottom: 20 }}>
          <strong>Comparison needs the API.</strong> {state.error} The map and
          station history keep working from the bundled snapshot — only this
          screen and alerts need a live query.
        </div>
      )}

      {state.error && !state.offline && (
        <div className="notice notice-bad" style={{ marginBottom: 20 }}>{state.error}</div>
      )}

      {state.loading && (
        <div className="skel" style={{ height: 300, border: "1px solid var(--hair)" }} />
      )}

      {state.data && !state.loading && (
        <>
          <CompareChart data={state.data} parameter={parameter} />

          <div style={{ overflowX: "auto", marginTop: 32 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>City</th>
                  <th className="r">Mean</th>
                  <th className="r">Min</th>
                  <th className="r">Max</th>
                  <th>Band of the mean</th>
                  <th className="r">Days with data</th>
                  <th className="r">Stations</th>
                </tr>
              </thead>
              <tbody>
                {state.data.cities.map((c) => (
                  <tr key={c.city}>
                    <td style={{
                      fontFamily: "var(--font-head)", fontWeight: 600,
                      textTransform: "uppercase", fontSize: 18,
                      color: c.found ? "var(--ink)" : "var(--mute)",
                    }}>
                      {c.city}
                      {!c.found && (
                        <span style={{
                          fontFamily: "var(--font-body)", textTransform: "none",
                          fontSize: 12, color: "var(--b5)", marginLeft: 10,
                        }}>
                          no data
                        </span>
                      )}
                    </td>
                    <td className="r">{fmtNum(c.summary.mean_value)}</td>
                    <td className="r" style={{ color: "var(--mute)" }}>
                      {fmtNum(c.summary.min_value)}
                    </td>
                    <td className="r">{fmtNum(c.summary.max_value)}</td>
                    <td><BandChip band={c.summary.band} withheld={
                      c.found ? null : "no data in range"} /></td>
                    <td className="r" style={{ color: "var(--mute)" }}>
                      {c.summary.n_days_present} / {c.summary.n_days_requested}
                      <span style={{ fontSize: 11 }}> ({fmtPct(c.summary.coverage_pct)})</span>
                    </td>
                    <td className="r" style={{ color: "var(--mute)" }}>
                      {c.summary.max_stations}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="kicker" style={{
            marginTop: 16, textTransform: "none", letterSpacing: 0, maxWidth: "70ch",
          }}>
            "Band of the mean" bands the average over the whole window, which is
            not the same as how often the city was in that band. A city
            averaging Moderate can still have spent thirty days Severe.
          </p>
        </>
      )}
    </div>
  )
}
