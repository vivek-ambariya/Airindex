/**
 * A unit string, never uppercased.
 *
 * This exists because of a real bug: units were being rendered inside
 * .kicker, which carries `text-transform: uppercase`. That turned
 * "µg/m³" into "MG/M³" on screen -- a different unit, off by a factor
 * of a thousand. A reader would have had no way to know the label was
 * wrong.
 *
 * Wrapping every unit in this component makes the mistake impossible to
 * repeat: the class re-asserts `text-transform: none` regardless of what
 * the surrounding text style does.
 */
export default function Unit({ children }) {
  return <span className="unit">{children}</span>
}
