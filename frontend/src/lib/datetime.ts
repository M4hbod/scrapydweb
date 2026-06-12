// Backend timestamps are emitted as naive strings on the server clock (UTC) --
// e.g. "2026-06-12 00:11:53" -- or, for apscheduler next-run times, with an
// explicit "+00:00" offset. The browser should show them in the viewer's local
// timezone, so parse them as UTC (unless an offset is already present) and
// format with the user's locale.

const HAS_TZ = /[zZ]|[+-]\d{2}:?\d{2}$/

export function parseServerDate(s?: string | null): Date | null {
  if (!s) return null
  let t = s.trim()
  if (!t) return null
  // "YYYY-MM-DD HH:MM:SS" -> ISO
  if (t.includes(" ") && !t.includes("T")) t = t.replace(" ", "T")
  // no timezone info -> the server clock is UTC
  if (!HAS_TZ.test(t)) t += "Z"
  const d = new Date(t)
  return isNaN(d.getTime()) ? null : d
}

// Full local date+time, e.g. "2026-06-12 04:01:48" in the viewer's tz.
export function fmtDateTime(s?: string | null, fallback = "–"): string {
  const d = parseServerDate(s)
  if (!d) return s || fallback
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
}
