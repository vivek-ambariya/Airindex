import { BAND_COLOURS, BAND_NAMES, NO_BAND_COLOUR, UNITS, bandRange } from "../lib/bands"
import Unit from "./Unit"

/**
 * Fixed colour bands, with the concentration range spelled out next to
 * each one. The mockups are firm about this: the band is meaningless
 * without the number it stands for, so the legend states both.
 */
export default function BandLegend({ parameter = "pm25", compact = false }) {
  return (
    <div>
      <div className="kicker" style={{ marginBottom: 8 }}>
        Bands · CPCB 24-hour · <Unit>{UNITS[parameter]}</Unit>
      </div>
      {/* Capped column width. auto-fit with 1fr let each cell grow to
          fill a 1500px row, which pushed every band's range so far from
          its label that the pairing stopped reading as a pair. */}
      <div style={{
        display: "grid",
        gridTemplateColumns: compact
          ? "1fr 1fr"
          : "repeat(auto-fit, minmax(150px, 190px))",
        gap: "6px 18px",
      }}>
        {BAND_NAMES.map((name, i) => (
          <span key={name} className="chip">
            <i style={{ background: BAND_COLOURS[i] }} aria-hidden="true" />
            <span>{name}</span>
            <span className="num" style={{ color: "var(--mute)", marginLeft: "auto" }}>
              {bandRange(parameter, i)}
            </span>
          </span>
        ))}
        <span className="chip" style={{ gridColumn: compact ? "span 2" : "auto" }}>
          <i className="no-band" style={{ background: NO_BAND_COLOUR }} aria-hidden="true" />
          <span>No band</span>
          <span style={{ color: "var(--mute)", marginLeft: "auto", fontSize: 11 }}>
            under 50% complete
          </span>
        </span>
      </div>
    </div>
  )
}
