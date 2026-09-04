import { useEffect, useRef, useState } from "react"
import { api } from "../lib/api"
import { PARAMETER_LABELS, THRESHOLDS, UNITS } from "../lib/bands"
import { fmtNum } from "../lib/format"
import Blueprint from "./Blueprint"
import Unit from "./Unit"

const PROMISES = [
  ["Daily averages only", "Thresholds are checked against the 24-hour mean, not a live reading. There is no minute-by-minute alerting here."],
  ["One station, one threshold", "Set several alerts if you want several stations. Each is confirmed and removed separately."],
  ["Silence when data stops", "On days a station reports too few hours you hear nothing. Silence means no usable data — never that the air is clean."],
  ["Deleted on unsubscribe", "Unsubscribing removes the address and the record of what was sent, not just a flag on a row."],
]

export default function Alerts({ snapshot, parameter }) {
  const [form, setForm] = useState({ email: "", stationId: "", threshold: "" })
  const [errors, setErrors] = useState({})
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tokenResult, setTokenResult] = useState(null)

  // Handle the verify / unsubscribe links the stubbed emails contain.
  //
  // The ref guard is load-bearing, not defensive noise. React StrictMode
  // runs effects twice in development, which fired verify twice: the
  // first call activated the subscription and the second came back
  // "already verified" -- so a reader clicking a fresh link was told
  // their alert was already on. The endpoint is idempotent so no data
  // was harmed, but the message was wrong, and for unsubscribe the
  // second call 404s on a row the first one just deleted.
  const redeemed = useRef(false)
  useEffect(() => {
    if (redeemed.current) return
    const token = new URLSearchParams(window.location.search).get("token")
    if (!token) return
    const path = window.location.pathname
    if (!path.includes("verify") && !path.includes("unsubscribe")) return
    redeemed.current = true

    const kind = path.includes("verify") ? "verify" : "unsubscribe"
    const call = kind === "verify" ? api.verify : api.unsubscribe
    call(token).then((res) => setTokenResult({ kind, ...res }))
  }, [])

  const stations = snapshot.stations
  const selected = stations.find((s) => String(s.id) === form.stationId)
  const suggested = THRESHOLDS[parameter][2] // the Moderate ceiling

  const validate = () => {
    const next = {}
    if (!form.email.trim()) next.email = "An email address is required."
    else if (!/^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(form.email.trim()))
      next.email = "That does not look like an email address."
    if (!form.stationId) next.stationId = "Pick a station."
    const t = Number(form.threshold)
    if (!form.threshold.trim()) next.threshold = "Set a threshold."
    else if (!Number.isFinite(t) || t < 1 || t > 2000)
      next.threshold = `Give a number between 1 and 2000 ${UNITS[parameter]}.`
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const submit = async (e) => {
    e.preventDefault()
    setResult(null)
    if (!validate()) return
    setBusy(true)
    const res = await api.subscribe({
      email: form.email.trim(),
      station_id: Number(form.stationId),
      parameter,
      threshold: Number(form.threshold),
    })
    setBusy(false)
    if (res.ok) {
      setResult({ tone: res.data.status === "already_exists" ? "dupe" : "ok",
                  message: res.data.message })
      if (res.data.status !== "already_exists") {
        setForm((f) => ({ ...f, email: "" }))
      }
    } else if (res.offline) {
      setResult({ tone: "offline", message: res.error })
    } else if (res.data?.field) {
      // Server-side errors land under their own field, matching the
      // client-side ones, rather than in a banner at the top.
      setErrors({ [res.data.field === "station_id" ? "stationId" : res.data.field]: res.error })
    } else {
      setResult({ tone: "bad", message: res.error })
    }
  }

  return (
    <div className="screen">
      <div className="screen-head">
        <div className="kicker">Double opt-in · stubbed delivery</div>
        <h1 style={{ marginTop: 10 }}>Alerts</h1>
        <p>
          Get told when a station's daily average crosses a number you choose.
          Nothing is active until you click the link in the confirmation email.
        </p>
      </div>

      <div className="notice" style={{ marginBottom: 28 }}>
        <strong>Mail is not actually sent in this build.</strong> Every message
        is written to <code>logs/emails.log</code> and printed by the Flask
        process. Open that file to find your confirmation link.
      </div>

      {tokenResult && (
        <Blueprint
          className={tokenResult.ok ? "" : "notice-bad"}
          style={{ padding: 16, marginBottom: 28 }}
        >
          <div className="kicker" style={{ marginBottom: 6 }}>
            {tokenResult.kind === "verify" ? "Confirmation" : "Unsubscribe"}
          </div>
          <p style={{ margin: 0 }}>
            {tokenResult.ok
              ? tokenResult.data.message
              : tokenResult.error}
          </p>
        </Blueprint>
      )}

      <div className="grid" style={{
        gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
        gap: "var(--s7)", alignItems: "start",
      }}>
        <Blueprint as="form" style={{ padding: 20 }} onSubmit={submit} noValidate>
          <div className="kicker" style={{ marginBottom: 16 }}>New alert</div>

          <div className="field" style={{ marginBottom: 16 }}>
            <label htmlFor="a-email">Email</label>
            <input
              id="a-email" className="input" type="email" autoComplete="email"
              value={form.email}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "a-email-err" : undefined}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              placeholder="you@example.com"
            />
            {errors.email && (
              <span className="field-error" id="a-email-err">{errors.email}</span>
            )}
          </div>

          <div className="field" style={{ marginBottom: 16 }}>
            <label htmlFor="a-station">Station</label>
            <select
              id="a-station" className="input" value={form.stationId}
              aria-invalid={!!errors.stationId}
              aria-describedby={errors.stationId ? "a-station-err" : undefined}
              onChange={(e) => setForm((f) => ({ ...f, stationId: e.target.value }))}
            >
              <option value="">Choose a station…</option>
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.city ? ` — ${s.city}` : ""}
                </option>
              ))}
            </select>
            {errors.stationId && (
              <span className="field-error" id="a-station-err">{errors.stationId}</span>
            )}
            {selected?.silent && (
              <span className="field-error">
                This station has stopped reporting. An alert on it will stay
                silent until it comes back.
              </span>
            )}
          </div>

          <div className="field" style={{ marginBottom: 8 }}>
            <label htmlFor="a-threshold">
              Threshold · {PARAMETER_LABELS[parameter]} in <Unit>{UNITS[parameter]}</Unit>
            </label>
            <input
              id="a-threshold" className="input" type="number" min="1" max="2000"
              step="1" inputMode="decimal"
              value={form.threshold}
              aria-invalid={!!errors.threshold}
              aria-describedby="a-threshold-help"
              onChange={(e) => setForm((f) => ({ ...f, threshold: e.target.value }))}
              placeholder={String(suggested)}
            />
            {errors.threshold && (
              <span className="field-error">{errors.threshold}</span>
            )}
            <span id="a-threshold-help" style={{ fontSize: 12, color: "var(--mute)" }}>
              {suggested} {UNITS[parameter]} is the top of the Moderate band.
              {selected?.latest_value != null && (
                <> This station's latest daily mean was{" "}
                  {fmtNum(selected.latest_value)}.</>
              )}
            </span>
          </div>

          <button className="btn btn-primary btn-block" type="submit"
                  disabled={busy}
                  style={{ width: "100%", marginTop: 18, padding: "11px 14px" }}>
            {busy ? "Sending confirmation…" : "Send me the confirmation link"}
          </button>

          {result && (
            <p style={{
              marginTop: 14, marginBottom: 0, fontSize: 13,
              color: result.tone === "ok" ? "var(--b2)"
                : result.tone === "dupe" ? "var(--b3)" : "var(--b5)",
            }}>
              {result.tone === "dupe" && <strong>No second email. </strong>}
              {result.message}
            </p>
          )}
        </Blueprint>

        <div>
          <div className="kicker" style={{ marginBottom: 14 }}>What you are signing up to</div>
          {PROMISES.map(([title, body]) => (
            <div key={title} style={{
              padding: "16px 0", borderBottom: "1px solid var(--hair)",
            }}>
              <h3 style={{ fontSize: 20, marginBottom: 6 }}>{title}</h3>
              <p style={{ margin: 0, fontSize: 14, color: "var(--mute)" }}>{body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
