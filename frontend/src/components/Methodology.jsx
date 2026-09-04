import { UNITS } from "../lib/bands"
import { fmtDate, fmtInt } from "../lib/format"
import BandLegend from "./BandLegend"
import Blueprint from "./Blueprint"
import Unit from "./Unit"

const RULES = [
  ["Negative values", "A concentration cannot be negative. Dropped."],
  ["Zeros in PM2.5 and PM10", "An exact zero is an instrument reporting nothing, not air containing nothing. Dropped for particulates; gases can legitimately read zero."],
  ["Sentinels: 999, 9999, −999", "Legacy no-data markers that pass through as if they were measurements. Dropped explicitly, because 999 µg/m³ is not physically impossible and a plausibility rule would not catch it."],
  ["PM2.5 above 1000, PM10 above 2000", "Beyond any credible ambient reading, including a severe episode. Dropped."],
  ["The same value six hours running", "A stuck sensor. The whole run is dropped. This is the most dangerous category, because it looks like data — plausible magnitude, and it fills the hole that would otherwise be visible."],
  ["Days built from under six hours", "Kept, not dropped. A sparse day is still information; it just cannot carry a colour. It is marked low-completeness and drawn grey."],
]

export default function Methodology({ snapshot, parameter }) {
  const meta = snapshot.meta
  return (
    <div className="screen">
      <div className="screen-head">
        <div className="kicker">How this was built</div>
        <h1 style={{ marginTop: 10 }}>Methodology</h1>
        <p>
          What the numbers are, how they were cleaned, and what they cannot
          tell you. The full write-up with the regression is in{" "}
          <code>docs/methodology.md</code>; the drop counts are in{" "}
          <code>docs/data_quality_report.md</code>.
        </p>
      </div>

      {meta.provenance.synthetic && (
        <div className="notice notice-bad" style={{ marginBottom: 30 }}>
          <strong>These measurements are synthetic.</strong>{" "}
          {/* The banner from paths.py opens with its own "SYNTHETIC
              MEASUREMENTS." sentence, which duplicates the bold lead-in
              above. Drop the first sentence and keep the substance. */}
          {String(meta.provenance.warning || "")
            .replace(/^SYNTHETIC MEASUREMENTS\.\s*/i, "")}
        </div>
      )}

      <div className="grid" style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", marginBottom: 40,
      }}>
        {[
          ["Source", meta.provenance.mode === "api" ? "OpenAQ v3" : "Generated fixture"],
          ["Window", `${fmtDate(meta.start)} — ${fmtDate(meta.end)}`],
          ["Stations", fmtInt(meta.n_stations)],
          ["Daily values", fmtInt(meta.n_points)],
          ["Unit", <Unit key="u">{UNITS[parameter]}</Unit>],
          ["Completeness floor", `${meta.completeness_floor}%`],
        ].map(([label, value]) => (
          <Blueprint key={label} className="stat">
            <div style={{
              fontFamily: "var(--font-head)", fontWeight: 600, fontSize: 22,
              textTransform: "uppercase",
            }}>
              {value}
            </div>
            <div className="kicker stat-l">{label}</div>
          </Blueprint>
        ))}
      </div>

      <h2 style={{ fontSize: 26, marginBottom: 8 }}>Concentrations, not an index</h2>
      <p style={{ maxWidth: "68ch", color: "var(--mute)" }}>
        Everything here is a 24-hour mean in {UNITS[parameter]}. The AQI number
        you may be used to is a piecewise transform of exactly this quantity
        onto a 0–500 scale, and converting to it loses the thing a reader can
        check against a standard. The bands below are the CPCB category
        breakpoints stated as concentration ranges instead.
      </p>
      <div style={{ marginTop: 22, maxWidth: 620 }}>
        <BandLegend parameter={parameter} />
      </div>

      <hr className="hr" />

      <h2 style={{ fontSize: 26, marginBottom: 8 }}>Four rules that drop, two that do not</h2>
      <p style={{ maxWidth: "68ch", color: "var(--mute)", marginBottom: 20 }}>
        Every dropped hour is attributed to exactly one rule, in this order, so
        the counts in the quality report sum to the total rather than
        double-counting overlaps. An hour reading −999 is counted as negative,
        not as a sentinel.
      </p>
      {RULES.map(([title, body], i) => (
        <div key={title} style={{
          display: "grid", gridTemplateColumns: "36px minmax(0,1fr)",
          gap: 16, padding: "16px 0", borderBottom: "1px solid var(--hair)",
        }}>
          <div className="num" style={{
            fontFamily: "var(--font-head)", fontSize: 22,
            color: i < 5 ? "var(--accent)" : "var(--b3)",
          }}>
            {i + 1}
          </div>
          <div>
            <h3 style={{ fontSize: 19, marginBottom: 5 }}>{title}</h3>
            <p style={{ margin: 0, fontSize: 14, color: "var(--mute)" }}>{body}</p>
          </div>
        </div>
      ))}

      <hr className="hr" />

      <h2 style={{ fontSize: 26, marginBottom: 8 }}>What this cannot show you</h2>
      <div className="grid" style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", marginTop: 18,
      }}>
        {[
          ["A gap is not clean air",
           "The single most important thing on this site. A station that stops transmitting still has a last recorded value, and a map that colours it green shows clean air where there is no instrument. Anything under 50% completeness is grey and carries no band, and the reason is always stated."],
          ["Station siting is not recorded",
           "A roadside monitor and a background monitor a kilometre apart measure genuinely different air, and nothing in this dataset distinguishes them. City averages mix the two."],
          ["A city average is a mean of monitors",
           "Not of people, and not of area. Delhi has several stations here and Kochi has one, so the national figure leans towards wherever the network is dense — which is the polluted north."],
          ["State is a lookup, not source data",
           "OpenAQ gives a country and a locality, never a state. The state column comes from a city-to-state table in the collector, and is empty where the city is not in it."],
          ["Daily means hide the peaks",
           "A day averaging Moderate can contain hours that were Severe. Hourly data exists upstream; this application deliberately reports the daily figure the standards are written against."],
          ["Concentration is not exposure",
           "Ambient outdoor concentration at a fixed monitor is not what any individual breathes. Indoor air, commuting, and cooking fuel all matter and none of them are here."],
        ].map(([title, body]) => (
          <Blueprint key={title} style={{ padding: 18 }}>
            <h3 style={{ fontSize: 19, marginBottom: 8 }}>{title}</h3>
            <p style={{ margin: 0, fontSize: 13.5, color: "var(--mute)" }}>{body}</p>
          </Blueprint>
        ))}
      </div>

      <hr className="hr" />

      <h2 style={{ fontSize: 26, marginBottom: 12 }}>Provenance</h2>
      <table className="table" style={{ maxWidth: 640 }}>
        <tbody>
          <tr><td style={{ color: "var(--mute)" }}>Collection mode</td>
              <td>{meta.provenance.mode || "unknown"}</td></tr>
          <tr><td style={{ color: "var(--mute)" }}>Collected</td>
              <td className="num">{meta.provenance.collected_at_utc || "—"}</td></tr>
          <tr><td style={{ color: "var(--mute)" }}>Snapshot generated</td>
              <td className="num">{meta.generated_at_utc}</td></tr>
          <tr><td style={{ color: "var(--mute)" }}>Bands</td>
              <td>{meta.bands.source}</td></tr>
        </tbody>
      </table>
    </div>
  )
}
