import { BAND_COLOURS, BAND_NAMES, NO_BAND_COLOUR } from "../lib/bands"

/**
 * A band, always as colour PLUS text.
 *
 * Colour is never the only channel carrying this information — the
 * label is always present, and the withheld state is additionally
 * hatched, so the distinction survives greyscale and colour blindness.
 */
export default function BandChip({ band, withheld, title }) {
  const i = band ? BAND_NAMES.indexOf(band) : -1
  return (
    <span className="chip" title={title || withheld || band || undefined}>
      <i
        className={band ? "" : "no-band"}
        style={{ background: band ? BAND_COLOURS[i] : NO_BAND_COLOUR }}
        aria-hidden="true"
      />
      <span>{band || "No band"}</span>
    </span>
  )
}
