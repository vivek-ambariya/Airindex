/**
 * CPCB air quality bands.
 *
 * This table is duplicated from backend/app/bands.py, deliberately: the
 * map has to render from the bundled snapshot with Flask stopped, so it
 * cannot ask the server what the thresholds are. Two copies is two
 * chances to disagree, so backend/tests/test_bands.py parses THIS FILE
 * and asserts the numbers match. Change one, change both, or the test
 * fails.
 *
 * Units: ug/m3, except CO in mg/m3.
 */
export const THRESHOLDS = {
  pm25: [30, 60, 90, 120, 250],
  pm10: [50, 100, 250, 350, 430],
  no2: [40, 80, 180, 280, 400],
  so2: [40, 80, 380, 800, 1600],
  o3: [50, 100, 168, 208, 748],
  co: [1, 2, 10, 17, 34],
}

export const BAND_NAMES = ["Good", "Satisfactory", "Moderate", "Poor", "Very poor", "Severe"]

export const BAND_COLOURS = ["#157F73", "#4FA79A", "#E6C351", "#E08A3C", "#C9497C", "#7E3A9E"]

/** Grey. Means "not measured well enough to say", never "clean". */
export const NO_BAND_COLOUR = "#4A4A4A"

export const UNITS = {
  pm25: "µg/m³", pm10: "µg/m³", no2: "µg/m³",
  so2: "µg/m³", o3: "µg/m³", co: "mg/m³",
}

export const PARAMETER_LABELS = {
  pm25: "PM2.5", pm10: "PM10", no2: "NO₂",
  so2: "SO₂", o3: "O₃", co: "CO",
}

export const MIN_COMPLETENESS_FOR_BAND = 50

export function bandIndex(parameter, value) {
  const cuts = THRESHOLDS[parameter]
  if (!cuts) return 5
  for (let i = 0; i < cuts.length; i += 1) {
    if (value <= cuts[i]) return i
  }
  return 5
}

/** The concentration range a band covers, for the legend. */
export function bandRange(parameter, i) {
  const cuts = THRESHOLDS[parameter]
  if (i === 5) return `${cuts[4]}+`
  const lo = i === 0 ? 0 : cuts[i - 1]
  return `${lo}–${cuts[i]}`
}

/**
 * Colour for a station marker.
 *
 * Grey whenever a band cannot be justified. A station that stopped
 * transmitting still has a last recorded value; painting it green would
 * put clean air on the map where there is no working instrument.
 */
export function stationColour(station) {
  return station.band ? BAND_COLOURS[BAND_NAMES.indexOf(station.band)] : NO_BAND_COLOUR
}

export function bandColourFor(parameter, value, lowCompleteness = false) {
  if (value == null || lowCompleteness) return NO_BAND_COLOUR
  return BAND_COLOURS[bandIndex(parameter, value)]
}
