// Serialization for the Run Spider form + client-side curl preview.

export const LATEST = "default: the latest version"

export interface SettingRow {
  key: string
  value: string
}

export interface ArgRow {
  key: string
  value: string
}

export interface ScheduleFormValues {
  project: string
  _version: string
  spider: string
  jobid: string
  nodes: number[]
  settings: SettingRow[]
  args: ArgRow[]
  mode: "now" | "cron"
  name: string
  action: "add_fire" | "add" | "add_pause"
  // >0 when editing an existing timer task (replace_existing path); 0/absent = create
  taskId?: number
  year: string
  month: string
  day: string
  week: string
  day_of_week: string
  hour: string
  minute: string
  second: string
}

// mirror backend LEGAL_NAME_PATTERN: [^0-9A-Za-z_-] -> '-'
export function sanitizeJobid(s: string) {
  return s.replace(/[^0-9A-Za-z_-]/g, "-")
}

export function buildScheduleForm(v: ScheduleFormValues): Record<string, string> {
  const out: Record<string, string> = {
    project: v.project,
    _version: v._version || LATEST,
    spider: v.spider,
    jobid: v.jobid,
    settings_json: JSON.stringify(v.settings.filter((s) => s.key && s.value)),
    args_json: JSON.stringify(
      Object.fromEntries(v.args.filter((a) => a.key && a.value).map((a) => [a.key, a.value])),
    ),
    checked_amount: String(v.nodes.length),
  }
  for (const n of v.nodes) out[String(n)] = "on"
  if (v.mode === "cron") {
    out.trigger = "cron"
    out.action = v.action
    out.name = v.name
    if (v.taskId) {
      out.task_id = String(v.taskId)
      out.replace_existing = "True"
    }
    out.year = v.year
    out.month = v.month
    out.day = v.day
    out.week = v.week
    out.day_of_week = v.day_of_week
    out.hour = v.hour
    out.minute = v.minute
    out.second = v.second
  }
  return out
}

// Equivalent request against the scrapydweb backend (not scrapyd): the same
// /{node}/schedule/group/ call the UI makes, so it recreates this exact job or
// timer task. Works for a single spider (Run Spider) or many (Run Group).
export function backendGroupCurl(
  node: number,
  body: Record<string, unknown>,
  origin: string,
): string {
  const json = JSON.stringify(body, null, 2)
  return [
    `curl -X POST '${origin}/${node}/schedule/group/' \\`,
    `  -H 'Content-Type: application/json' \\`,
    `  -b cookies.txt \\`, // session cookie from POST /api/auth/login
    `  -d '${json}'`,
  ].join("\n")
}

function shellQuote(s: string) {
  return /[^A-Za-z0-9_\-.=:/@]/.test(s) ? `'${s.replace(/'/g, "'\\''")}'` : s
}

// Mirrors backend generate_cmd(): sorted settings, sanitized jobid,
// _version omitted when latest. Auth is added server-side and shown as a hint.
export function buildCurlPreview(v: ScheduleFormValues, server: string): string {
  const parts: string[] = [`curl http://${server}/schedule.json`]
  const push = (kv: string, urlencode = false) => {
    const flag = urlencode || /[\s"']/.test(kv) ? "--data-urlencode" : "-d"
    parts.push(`${flag} ${shellQuote(kv)}`)
  }
  push(`project=${v.project || "?"}`)
  if (v._version && v._version !== LATEST) push(`_version=${v._version}`)
  push(`spider=${v.spider || "?"}`)
  push(`jobid=${v.jobid ? sanitizeJobid(v.jobid) : "<auto: timestamp>"}`)
  const settings = v.settings
    .filter((s) => s.key && s.value)
    .map((s) => `${s.key}=${s.value}`)
    .sort()
  for (const s of settings) push(`setting=${s}`)
  for (const a of v.args.filter((a) => a.key && a.value)) push(`${a.key}=${a.value}`)
  return parts.join(" \\\n  ")
}
