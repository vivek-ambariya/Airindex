import { useMemo, useState } from "react"
import { UNITS, PARAMETER_LABELS } from "../lib/bands"
import { fmtDate, fmtNum, fmtPct, dateAt } from "../lib/format"
import BandChip from "./BandChip"
import Blueprint from "./Blueprint"
import MonthlyChart from "./MonthlyChart"
import SeriesChart from "./SeriesChart"
import Unit from "./Unit"

/** The API returns withheld-reasons lowercase, to sit after a comma.
 *  Here one starts a sentence, so it needs a capital. */
const sentence = (text) =>
  !text ? text : text.charAt(0).toUpperCase() + text.slice(1)

const RANGES = [
  { label: "90d", days: 90 },
  { label: "1y", days: 365 },
  { label: "5y", days: null },
]

/** The empty state. Slots held, values withheld — the mockup is
 *  explicit that nothing should be invented before a selection. */
function Empty() {
  return (
    <div>
      <div className="kicker">Nothing selected yet</div>
      <h2 style={{ fontSize: 30, margin: "10px 0 12px" }}>Tap a station</h2>
      <p style={{ color: "var(--mute)", fontSize: 14 }}>
        Pick a marker to see its latest daily average, its five-year record and
        its seasonal profile. Click anywhere else and the map reports the
        nearest station and how far away it is.
      </p>
      <div style={{ marginTop: 24, display: "grid", gap: 10 }}>
        {["Latest daily average", "Five-year record", "Seasonal profile"].map((label) => (
          <div key={label}>
            <div className="kicker" style={{ marginBottom: 6 }}>{label}</div>
            <div className="skel" style={{ height: 34, border: "1px solid var(--hair)" }} />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function StationPanel({
  station, snapshot, parameter, probeResult, onClearProbe, onSelect,
}) {
  const [rangeDays, setRangeDays] = useState(365)

  const sliced = useMemo(() => {
    if (!station) return null
    const all = station.values
    const n = rangeDays == null ? all.length : Math.min(rangeDays, all.length)
    const offset = all.length - n
    return {
      values: all.slice(offset),
      startISO: dateAt(snapshot.meta.start, offset),
      low: station.low_completeness
        .filter((i) => i >= offset)
        .map((i) => i - offset),
    }
  }, [station, rangeDays, snapshot])

  return (
    <>
      {probeResult && (
        <Blueprint
          className={probeResult.found ? "" : "notice-bad"}
          style={{ padding: 14, marginBottom: 20 }}
        >
          <div className="kicker" style={{ marginBottom: 6 }}>
            {probeResult.found ? "Nearest station" : "Nothing within range"}
          </div>
          {probeResult.found ? (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <button
                  className="nav-link"
                  style={{
                    fontFamily: "var(--font-head)", fontSize: 24, color: "var(--ink)",
                    letterSpacing: 0, padding: 0,
                  }}
                  onClick={() => onSelect(probeResult.station.id)}
                >
                  {probeResult.station.name}
                </button>
                <span className="num" style={{ color: "var(--accent)", fontSize: 15 }}>
                  {fmtNum(probeResult.station.distance_km, 1)} km
                </span>
              </div>
              <div style={{ fontSize: 13, color: "var(--mute)", marginTop: 4 }}>
                {probeResult.station.city}
                {probeResult.offline && " · measured in the browser, API offline"}
              </div>
            </>
          ) : (
            <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink)" }}>
              {probeResult.message}
            </p>
          )}
          {!probeResult.found && (
            <p style={{ margin: "10px 0 0", fontSize: 13, color: "var(--mute)" }}>
              Try clicking closer to a city, or widen the radius.
            </p>
          )}
          <button className="btn" style={{ marginTop: 12 }} onClick={onClearProbe}>
            Clear
          </button>
        </Blueprint>
      )}

      {!station ? <Empty /> : (
        <div>
          <div className="kicker">{station.city}{station.state ? ` · ${station.state}` : ""}</div>
          <h2 style={{ fontSize: "clamp(26px,3vw,38px)", margin: "8px 0 14px" }}>
            {station.name}
          </h2>

          {/* Latest value */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
            <div>
              <div className="stat-v num" style={{ fontSize: 46 }}>
                {station.latest_value == null ? "—" : fmtNum(station.latest_value)}
              </div>
              <div className="kicker" style={{ marginTop: 2 }}>
                {PARAMETER_LABELS[parameter]} · <Unit>{UNITS[parameter]}</Unit> · daily mean
              </div>
            </div>
            <div style={{ marginBottom: 6 }}>
              <BandChip band={station.band} withheld={station.band_withheld} />
              <div style={{ fontSize: 12, color: "var(--mute)", marginTop: 6 }}>
                {fmtDate(station.latest_date)}
              </div>
            </div>
          </div>

          {/* The honesty line. Whenever a band is withheld, the reason
              is shown here rather than left as an unexplained grey. */}
          {station.band_withheld && (
            <div
              className={`notice ${station.silent ? "notice-bad" : "notice-warn"}`}
              style={{ marginTop: 14 }}
            >
              <strong>{station.silent ? "Silent, not clean." : "No band assigned."}</strong>{" "}
              {sentence(station.band_withheld)}. A colour here would be a claim
              this record cannot support.
            </div>
          )}

          {/* Completeness */}
          <div style={{
            display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 22,
          }}>
            <div>
              <div className="kicker">30-day completeness</div>
              <div className="num" style={{
                fontSize: 22, marginTop: 4,
                color: station.completeness_30d < 50 ? "var(--b5)" : "var(--ink)",
              }}>
                {fmtPct(station.completeness_30d)}
              </div>
            </div>
            <div>
              <div className="kicker">Reporting since</div>
              <div className="num" style={{ fontSize: 22, marginTop: 4 }}>
                {station.first_seen ? station.first_seen.slice(0, 4) : "—"}
              </div>
            </div>
          </div>

          {/* Series */}
          <div style={{ marginTop: 26 }}>
            <div style={{
              display: "flex", alignItems: "baseline", justifyContent: "space-between",
              marginBottom: 10, gap: 8, flexWrap: "wrap",
            }}>
              <div className="kicker">Daily record</div>
              <div style={{ display: "flex", gap: 6 }}>
                {RANGES.map((r) => (
                  <button
                    key={r.label}
                    className="btn"
                    style={{ padding: "5px 10px", fontSize: 11 }}
                    aria-pressed={rangeDays === r.days}
                    onClick={() => setRangeDays(r.days)}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
            <SeriesChart
              values={sliced.values}
              startISO={sliced.startISO}
              parameter={parameter}
              lowCompleteness={sliced.low}
              height={190}
            />
          </div>

          {/* Monthly */}
          <div style={{ marginTop: 30 }}>
            <div className="kicker" style={{ marginBottom: 10 }}>
              Seasonal profile · all years pooled
            </div>
            <MonthlyChart
              months={station.monthly}
              nDays={station.monthly_n_days}
              parameter={parameter}
            />
          </div>
        </div>
      )}
    </>
  )
}
