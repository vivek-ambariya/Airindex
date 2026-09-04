import { UNITS, bandColourFor } from "../lib/bands"
import { fmtNum, monthName } from "../lib/format"

const W = 380
const H = 132
const PAD = { t: 10, r: 4, b: 22, l: 30 }

/**
 * The seasonal profile: twelve monthly means pooled across every year.
 *
 * Bars are coloured by band, and each carries the number of days behind
 * it in its tooltip and in the accessible table. A month resting on 40
 * days and one resting on 400 look identical otherwise, and in this
 * dataset that difference is common.
 */
export default function MonthlyChart({ months, nDays = [], parameter = "pm25" }) {
  const present = months.filter((v) => v != null)
  if (!present.length) {
    return <p style={{ color: "var(--mute)", fontSize: 13 }}>No monthly profile available.</p>
  }
  const max = Math.max(...present) * 1.1
  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b
  const slot = innerW / 12
  const barW = slot * 0.62

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Monthly mean ${parameter}, January to December`}>
        <line x1={PAD.l} x2={W - PAD.r} y1={PAD.t + innerH} y2={PAD.t + innerH}
              className="grid-line" />
        <text x={PAD.l - 4} y={PAD.t + 8} className="axis-label" textAnchor="end">
          {Math.round(max)}
        </text>
        {months.map((v, i) => {
          if (v == null) {
            return (
              <text key={i} x={PAD.l + slot * i + slot / 2} y={PAD.t + innerH - 4}
                    className="axis-label" textAnchor="middle">–</text>
            )
          }
          const h = (v / max) * innerH
          const isWinter = i === 0 || i === 10 || i === 11
          return (
            <g key={i}>
              <rect
                x={PAD.l + slot * i + (slot - barW) / 2}
                y={PAD.t + innerH - h}
                width={barW}
                height={Math.max(h, 1)}
                fill={bandColourFor(parameter, v)}
                fillOpacity={isWinter ? 1 : 0.82}
              >
                <title>
                  {`${monthName(i + 1)}: ${fmtNum(v)} ${UNITS[parameter]}`}
                  {nDays[i] ? ` · from ${nDays[i]} days` : ""}
                </title>
              </rect>
            </g>
          )
        })}
        {months.map((_, i) => (
          <text key={`l${i}`} x={PAD.l + slot * i + slot / 2} y={H - 7}
                className="axis-label" textAnchor="middle"
                style={{ fontSize: 8.5 }}>
            {monthName(i + 1).charAt(0)}
          </text>
        ))}
      </svg>

      {/* The accessible fallback the chart guidance asks for: the same
          numbers as a real table, not only as SVG. */}
      <details style={{ marginTop: 6 }}>
        <summary className="kicker" style={{ cursor: "pointer" }}>
          Monthly figures as a table
        </summary>
        <table className="table" style={{ marginTop: 8, fontSize: 13 }}>
          <thead>
            <tr><th>Month</th><th className="r">Mean</th><th className="r">Days</th></tr>
          </thead>
          <tbody>
            {months.map((v, i) => (
              <tr key={i}>
                <td>{monthName(i + 1)}</td>
                <td className="r">{v == null ? "—" : fmtNum(v)}</td>
                <td className="r" style={{ color: "var(--mute)" }}>{nDays[i] || 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}
