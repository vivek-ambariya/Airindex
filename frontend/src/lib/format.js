export const fmtNum = (v, dp = 1) =>
  v == null ? "—" : Number(v).toLocaleString("en-IN", {
    minimumFractionDigits: dp, maximumFractionDigits: dp,
  })

export const fmtInt = (v) =>
  v == null ? "—" : Number(v).toLocaleString("en-IN")

export const fmtPct = (v, dp = 0) => (v == null ? "—" : `${Number(v).toFixed(dp)}%`)

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
export const monthName = (m) => MONTHS[m - 1] ?? "—"

export function fmtDate(iso) {
  if (!iso) return "—"
  const d = new Date(`${iso}T00:00:00Z`)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** Day offset -> ISO date, for indexing into the snapshot's arrays. */
export function dateAt(startISO, offset) {
  const d = new Date(`${startISO}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + offset)
  return d.toISOString().slice(0, 10)
}

export function daysBetween(startISO, endISO) {
  const a = new Date(`${startISO}T00:00:00Z`)
  const b = new Date(`${endISO}T00:00:00Z`)
  return Math.round((b - a) / 86400000)
}
