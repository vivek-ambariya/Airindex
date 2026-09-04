import { useMemo, useRef, useState } from "react"
import { BAND_COLOURS, THRESHOLDS, UNITS, bandColourFor } from "../lib/bands"
import { lttb } from "../lib/downsample"
import { dateAt, fmtDate, fmtNum } from "../lib/format"

const W = 760
const H = 210
const PAD = { t: 12, r: 8, b: 22, l: 38 }

/**
 * Daily values over time.
 *
 * Two things this chart refuses to do:
 *
 *  1. Interpolate across a gap. A missing week is drawn as a break in
 *     the line with a hatched band beneath it, never as a straight line
 *     between the days either side. A smooth line across a hole is a
 *     claim that nothing happened, which is not what missing data means.
 *
 *  2. Colour a low-completeness day. Those points are drawn grey and
 *     listed separately.
 *
 * Interaction is keyboard-reachable: arrow keys move the cursor, and the
 * readout below is always visible rather than depending on hover.
 */
export default function SeriesChart({
  values, startISO, parameter = "pm25", lowCompleteness = [], height = H,
}) {
  const svgRef = useRef(null)
  const [cursor, setCursor] = useState(null)

  const lowSet = useMemo(() => new Set(lowCompleteness), [lowCompleteness])

  const { points, max, present, firstIdx, lastIdx } = useMemo(() => {
    const withValues = values
      .map((v, i) => (v == null ? null : { i, v }))
      .filter(Boolean)
    const maxV = withValues.length
      ? Math.max(...withValues.map((p) => p.v))
      : 1
    return {
      points: lttb(values, 520),
      max: maxV,
      present: withValues.length,
      firstIdx: withValues.length ? withValues[0].i : 0,
      lastIdx: withValues.length ? withValues[withValues.length - 1].i : 0,
    }
  }, [values, lowCompleteness])

  if (!present) {
    return (
      <div className="notice notice-warn">
        No readings in this window. This is a gap in the record, not a
        measurement of clean air.
      </div>
    )
  }

  const innerW = W - PAD.l - PAD.r
  const innerH = height - PAD.t - PAD.b
  // Head-room so the peak is not flush against the top edge.
  const yMax = max * 1.12
  const x = (i) => PAD.l + (i / Math.max(values.length - 1, 1)) * innerW
  const y = (v) => PAD.t + innerH - (v / yMax) * innerH

  // Band thresholds as horizontal reference lines — they turn the y
  // axis from a bare number into the scale people are judged against.
  const cuts = THRESHOLDS[parameter].filter((c) => c <= yMax)

  // Build the path, breaking on nulls so gaps stay gaps.
  let d = ""
  let pen = false
  for (const p of points) {
    if (p === null) { pen = false; continue }
    d += `${pen ? "L" : "M"}${x(p.i).toFixed(1)} ${y(p.v).toFixed(1)}`
    pen = true
  }

  // Contiguous missing runs, for the hatched gap markers.
  const gaps = []
  let gapStart = null
  for (let i = 0; i <= values.length; i += 1) {
    const missing = i < values.length && values[i] == null
    if (missing && gapStart === null) gapStart = i
    if (!missing && gapStart !== null) {
      // Only mark gaps inside the reported span, and only if they are
      // long enough to be visible — single days would be noise.
      if (gapStart > firstIdx && i - 1 < lastIdx && i - gapStart >= 3) {
        gaps.push([gapStart, i - 1])
      }
      gapStart = null
    }
  }

  const move = (delta) => {
    setCursor((c) => {
      let i = (c == null ? lastIdx : c) + delta
      i = Math.max(0, Math.min(values.length - 1, i))
      return i
    })
  }

  const onPointer = (evt) => {
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((evt.clientX - rect.left) / rect.width) * W
    const frac = (px - PAD.l) / innerW
    const i = Math.round(frac * (values.length - 1))
    setCursor(Math.max(0, Math.min(values.length - 1, i)))
  }

  const active = cursor == null ? lastIdx : cursor
  const activeValue = values[active]
  const activeLow = lowSet.has(active)

  return (
    <div className="chart-wrap">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${height}`}
        role="img"
        aria-label={
          `Daily ${parameter} from ${fmtDate(startISO)}. ` +
          `${present} days with data out of ${values.length}. ` +
          `Peak ${fmtNum(max)} ${UNITS[parameter]}.`
        }
        tabIndex={0}
        onMouseMove={onPointer}
        onMouseLeave={() => setCursor(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") { move(1); e.preventDefault() }
          if (e.key === "ArrowLeft") { move(-1); e.preventDefault() }
          if (e.key === "Home") { setCursor(firstIdx); e.preventDefault() }
          if (e.key === "End") { setCursor(lastIdx); e.preventDefault() }
        }}
        style={{ cursor: "crosshair" }}
      >
        {/* band reference lines */}
        {cuts.map((cut, i) => (
          <g key={cut}>
            <line
              x1={PAD.l} x2={W - PAD.r} y1={y(cut)} y2={y(cut)}
              stroke={BAND_COLOURS[i]} strokeWidth="1" strokeOpacity="0.28"
              strokeDasharray="3 3"
            />
            <text x={PAD.l - 5} y={y(cut) + 3} className="axis-label" textAnchor="end">
              {cut}
            </text>
          </g>
        ))}

        {/* gaps, hatched — "the gap is the instrument" */}
        <defs>
          <pattern id="gapHatch" width="6" height="6" patternTransform="rotate(45)"
                   patternUnits="userSpaceOnUse">
            <rect width="6" height="6" fill="transparent" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#3a3a3a" strokeWidth="2" />
          </pattern>
        </defs>
        {gaps.map(([a, b]) => (
          <rect
            key={`${a}-${b}`}
            x={x(a)} y={PAD.t} width={Math.max(x(b) - x(a), 1.5)} height={innerH}
            fill="url(#gapHatch)"
          >
            <title>{`No data ${fmtDate(dateAt(startISO, a))} – ${fmtDate(dateAt(startISO, b))} (${b - a + 1} days)`}</title>
          </rect>
        ))}

        {/* baseline */}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="grid-line" />

        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.25"
              strokeLinejoin="round" />

        {/* low-completeness days marked individually, in grey */}
        {[...lowSet].filter((i) => values[i] != null).map((i) => (
          <circle key={i} cx={x(i)} cy={y(values[i])} r="1.6"
                  fill="var(--bx)" />
        ))}

        {/* cursor */}
        {activeValue != null && (
          <g>
            <line x1={x(active)} x2={x(active)} y1={PAD.t} y2={PAD.t + innerH}
                  className="chart-focus" />
            <circle cx={x(active)} cy={y(activeValue)} r="3.4"
                    fill={bandColourFor(parameter, activeValue, activeLow)}
                    stroke="var(--bg)" strokeWidth="1.5" />
          </g>
        )}

        <text x={PAD.l} y={height - 6} className="axis-label">
          {fmtDate(startISO)}
        </text>
        <text x={W - PAD.r} y={height - 6} className="axis-label" textAnchor="end">
          {fmtDate(dateAt(startISO, values.length - 1))}
        </text>
      </svg>

      {/* Always-visible readout. The tooltip is a convenience; this is
          the accessible path and does not require a pointer. */}
      <dl className="readout">
        <div>
          <dt>{cursor == null ? "Latest" : "Selected"}</dt>
          <dd>{fmtDate(dateAt(startISO, active))}</dd>
        </div>
        <div>
          <dt>Value</dt>
          <dd>
            {activeValue == null
              ? "no data"
              : `${fmtNum(activeValue)} ${UNITS[parameter]}`}
            {activeLow && (
              <span style={{ color: "var(--mute)" }}> · under 50% complete</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Peak in window</dt>
          <dd>{fmtNum(max)} {UNITS[parameter]}</dd>
        </div>
        <div>
          <dt>Days with data</dt>
          <dd>{present} of {values.length}</dd>
        </div>
      </dl>
      <p className="kicker" style={{ marginTop: 8, textTransform: "none", letterSpacing: 0 }}>
        Hover, or focus the chart and use ← →. Hatched columns are days with
        no reading; the line breaks rather than crossing them.
      </p>
    </div>
  )
}
