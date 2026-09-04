import { lttb } from "../lib/downsample"

/** A bare trend line for table rows. Decorative — every row it appears
 *  in also carries the number, so this is never the only channel. */
export default function Sparkline({ values, width = 150, height = 26, colour = "var(--accent)" }) {
  const present = values.filter((v) => v != null)
  if (present.length < 3) return null
  const max = Math.max(...present)
  const min = Math.min(...present)
  const span = max - min || 1
  const points = lttb(values, 90)

  let d = ""
  let pen = false
  for (const p of points) {
    if (p === null) { pen = false; continue }
    const x = (p.i / Math.max(values.length - 1, 1)) * width
    const y = height - ((p.v - min) / span) * (height - 2) - 1
    d += `${pen ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`
    pen = true
  }
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}
         aria-hidden="true" style={{ display: "block", overflow: "visible" }}>
      <path d={d} fill="none" stroke={colour} strokeWidth="1" strokeOpacity="0.75" />
    </svg>
  )
}
