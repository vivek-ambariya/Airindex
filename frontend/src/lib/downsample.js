/**
 * Largest-Triangle-Three-Buckets downsampling.
 *
 * Five years of daily values is ~1830 points. Drawing that into an
 * 800px-wide SVG asks the browser to render more than two points per
 * pixel, and past roughly 1000 points SVG path rendering gets visibly
 * slow on a mid-range machine.
 *
 * Naive every-Nth sampling is the wrong fix: it drops peaks, and the
 * peaks are the entire point of an air quality chart -- a severe episode
 * three days long would simply vanish. LTTB keeps the points that
 * preserve the visual shape, so spikes survive.
 *
 * Gaps (nulls) are NEVER interpolated away. They are preserved as
 * segment breaks so a hole in the data is drawn as a hole.
 */
export function lttb(values, threshold) {
  const n = values.length
  if (threshold >= n || threshold < 3) {
    return values.map((v, i) => ({ i, v }))
  }

  // Split on nulls, downsample each run in proportion to its length,
  // and keep the breaks. Running LTTB across a gap would draw a
  // straight line over missing weeks.
  const runs = []
  let current = []
  for (let i = 0; i < n; i += 1) {
    if (values[i] == null) {
      if (current.length) { runs.push(current); current = [] }
    } else {
      current.push({ i, v: values[i] })
    }
  }
  if (current.length) runs.push(current)

  const present = runs.reduce((sum, r) => sum + r.length, 0)
  if (present === 0) return []

  const out = []
  for (const run of runs) {
    const budget = Math.max(3, Math.round((run.length / present) * threshold))
    out.push(budget >= run.length ? run : lttbRun(run, budget))
  }
  // Flatten but keep a null between runs so the renderer breaks the path.
  return out.flatMap((run, idx) => (idx === 0 ? run : [null, ...run]))
}

function lttbRun(data, threshold) {
  const n = data.length
  const bucketSize = (n - 2) / (threshold - 2)
  const sampled = [data[0]]
  let a = 0

  for (let i = 0; i < threshold - 2; i += 1) {
    // Average of the next bucket, used as the third triangle vertex.
    const avgStart = Math.floor((i + 1) * bucketSize) + 1
    const avgEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, n)
    let avgI = 0, avgV = 0
    const avgCount = avgEnd - avgStart || 1
    for (let j = avgStart; j < avgEnd; j += 1) {
      avgI += data[j].i
      avgV += data[j].v
    }
    avgI /= avgCount
    avgV /= avgCount

    const rangeStart = Math.floor(i * bucketSize) + 1
    const rangeEnd = Math.floor((i + 1) * bucketSize) + 1
    const pointA = data[a]
    let best = rangeStart, bestArea = -1

    for (let j = rangeStart; j < Math.min(rangeEnd, n); j += 1) {
      const area = Math.abs(
        (pointA.i - avgI) * (data[j].v - pointA.v) -
        (pointA.i - data[j].i) * (avgV - pointA.v)
      )
      if (area > bestArea) { bestArea = area; best = j }
    }
    sampled.push(data[best])
    a = best
  }
  sampled.push(data[n - 1])
  return sampled
}

/** Monthly means, for the long-range view. Ignores nulls. */
export function monthlyMeans(values, startISO) {
  const buckets = new Map()
  const start = new Date(`${startISO}T00:00:00Z`)
  for (let i = 0; i < values.length; i += 1) {
    if (values[i] == null) continue
    const d = new Date(start)
    d.setUTCDate(d.getUTCDate() + i)
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`
    const b = buckets.get(key) || { sum: 0, n: 0 }
    b.sum += values[i]; b.n += 1
    buckets.set(key, b)
  }
  return [...buckets.entries()].map(([month, b]) => ({
    month, value: b.sum / b.n, n: b.n,
  }))
}
