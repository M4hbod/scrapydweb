// Typed fetch helpers for the scrapydweb JSON API.

export interface NodeInfo {
  node: number
  server: string
  group: string
  public_url: string
}

export interface DashboardKpi {
  running: number
  pending: number
  finished: number
  pages: number
  items: number
}

export interface DashboardNode {
  index: number
  server: string
  group: string
  running: number
  pending: number
  finished: number
  jobs_total: number
  pages: number
  items: number
  last: string
  load_pct: number
}

export interface ActivityEvent {
  node: number
  server: string
  project: string
  spider: string
  job: string
  status_label: string
  status_class: "run" | "pend" | "fin"
  pages: number | null
  items: number | null
  runtime: string | null
  when: string
}

export interface ThroughputBucket {
  label: string
  count: number
  pct: number
}

export interface Dashboard {
  nodes_total: number
  nodes_online: number
  kpi: DashboardKpi
  nodes: DashboardNode[]
  activity: ActivityEvent[]
  throughput: ThroughputBucket[]
  throughput_total: number
}

export interface JobRow {
  id: number
  project: string
  spider: string
  job: string
  status: "0" | "1" | "2"
  pid: number | null
  pages: number | null
  items: number | null
  version: string | null
  args: Record<string, string>
  finish_reason: string | null
  start: string | null
  finish: string | null
  runtime: string | null
  update_time: string | null
  href_log: string | null
  href_items: string | null
  url_stats: string
  url_log: string
  url_stop: string
  url_start: string
}

export interface JobsResponse {
  status: string
  node: number
  page: number
  per_page: number
  pages: number
  total: number
  jobs: JobRow[]
  warnings: string[]
  message?: string
}

export interface TaskRow {
  id: number
  name: string
  project: string
  version: string
  spider: string
  jobid: string
  trigger: string
  create_time: string
  update_time: string
  year: string
  month: string
  day: string
  week: string
  day_of_week: string
  hour: string
  minute: string
  second: string
  start_date: string | null
  end_date: string | null
  timezone: string | null
  settings_arguments: string
  selected_nodes: string
  status: "Running" | "Paused" | "Finished"
  next_run_time: string | null
  run_times: number
  fail_times: number
  prev_run_result: string
}

export interface ApiToken {
  id: number
  name: string
  prefix: string
  created_at: string | null
  last_used_at: string | null
}

export interface JobGroup {
  id: number
  name: string
  project: string
  version: string
  spiders: string[]
  nodes: number[]
  settings: { key: string; value: string }[]
  args: Record<string, string>
  notify_enabled: boolean
  notify_channels: string[]
  fire_path: string
  created_at: string | null
  updated_at: string | null
}

export interface TasksResponse {
  status: string
  page: number
  per_page: number
  total: number
  tasks: TaskRow[]
  scheduler_enabled: boolean
}

export interface TaskJobResult {
  id: number
  node: number
  server: string
  status_code: number
  status: string
  result: string
  run_time: string | null
}

export interface TaskResult {
  id: number
  execute_time: string | null
  fail_count: number
  pass_count: number
  job_results: TaskJobResult[]
}

export interface TaskResultsResponse {
  status: string
  task: { id: number; name: string; project: string; spider: string; jobid: string }
  page: number
  per_page: number
  total: number
  results: TaskResult[]
}

export interface LogTextResponse {
  status: string
  status_code?: number
  opt: string
  node: number
  project: string
  spider: string
  job: string
  finished: boolean
  version?: string | null
  url_source: string
  text: string
  last_update_timestamp: number | null
}

export interface LogCategory {
  count: number
  details?: unknown[]
}

export interface LogStatsResponse {
  status: string
  status_code?: number
  opt: string
  node: number
  project: string
  spider: string
  job: string
  finished: boolean
  version?: string | null
  args?: Record<string, string>
  url_source: string
  logparser_valid: boolean
  stats?: {
    pages: number | string | null
    items: number | string | null
    runtime: string | null
    finish_reason: string | null
    shutdown_reason: string | null
    first_log_time: string | null
    latest_log_time: string | null
    last_update_time: string | null
    log_categories?: Record<string, LogCategory>
    // logparser time-series for the crawl-progress chart:
    // [time, pages, pages/min, items, items/min]
    datas?: [string, number, number, number, number][]
    [key: string]: unknown
  }
}

export interface SettingFieldDto {
  key: string
  type: "bool" | "int" | "float" | "str" | "list_str" | "list_int" | "enum" | "secret" | "servers"
  label: string
  help: string
  default: unknown
  value: unknown
  source: "default" | "env" | "db" | "test"
  apply: "live" | "reschedule" | "resubprocess" | "restart"
  secret: boolean
  nullable: boolean
  choices: string[] | null
  min: number | null
  textarea: boolean
}

export interface SettingsGroupDto {
  id: string
  label: string
  fields: SettingFieldDto[]
}

export interface ServerRowDto {
  host: string
  port: number
  username: string
  password: string
  group: string
  public_url: string
}

export interface SettingsSchemaResponse {
  status: string
  groups: SettingsGroupDto[]
  servers_value: ServerRowDto[]
  pending_restart: string[]
  system_info: Record<string, unknown> & { databases: Record<string, string> }
}

export interface SaveSettingsResponse {
  status: string
  results?: Record<string, "applied" | "restart_required">
  errors?: Record<string, string>
  restart_required?: boolean
  nodes_changed?: boolean
}

export interface DeployNodeResult {
  node: number
  server: string
  status: string
  status_code: number
  message: string
}

export interface DeployRecord {
  id: number
  source: "file" | "folder" | "git" | "push" | "webhook"
  project: string
  version: string | null
  eggname: string | null
  status: "pending" | "ok" | "partial" | "error"
  actor: string | null
  repo_id: number | null
  message: string | null
  results: DeployNodeResult[]
  created_at: string | null
  finished_at: string | null
}

export type DeploySource = "manual" | "folder" | "git" | "webhook"

export interface Project {
  id: number
  name: string
  description: string
  deploy_source: DeploySource
  default_nodes: number[]
  repo_url: string
  ref: string
  has_token: boolean
  enabled: boolean
  webhook_secret: string | null
  webhook_path: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AlertThresholdSpec {
  threshold: number
  action: "alert" | "stop" | "forcestop" | null
}

export interface AlertRule {
  id: number
  name: string
  enabled: boolean
  project_pattern: string
  spider_pattern: string
  thresholds: Record<string, AlertThresholdSpec>
  on_finished: boolean | null
  on_running_interval: number | null
  channels: string[] | null
  created_at: string | null
  updated_at: string | null
}

export interface SearchResult {
  node: number
  server: string
  project: string
  spider: string
  job: string
  status_label: string
  status_class: "run" | "pend" | "fin"
  url: string
}

function redirectToLogin(res: Response, url: string) {
  if (
    res.status === 401 &&
    !url.startsWith("/api/auth") &&
    window.location.pathname !== "/login"
  ) {
    window.location.href = "/login"
    return true
  }
  return false
}

export async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } })
  if (redirectToLogin(res, url)) return new Promise<T>(() => {})
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return res.json() as Promise<T>
}

export async function postJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { Accept: "application/json" } })
  if (redirectToLogin(res, url)) return new Promise<T>(() => {})
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return res.json() as Promise<T>
}

export async function postJSONBody<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  const js = (await res.json()) as T
  if (!res.ok && ![400, 401, 403].includes(res.status))
    throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return js
}

export interface AuthMe {
  authenticated: boolean
  username: string | null
  setup_required: boolean
}

export async function putJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  const js = (await res.json()) as T & { errors?: Record<string, string> }
  if (!res.ok && res.status !== 400) throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return js
}

export async function deleteJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } })
  if (redirectToLogin(res, url)) return new Promise<T>(() => {})
  const js = (await res.json()) as T
  if (!res.ok && ![400, 404].includes(res.status))
    throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return js
}

export async function postForm<T>(url: string, fields: Record<string, string>): Promise<T> {
  const body = new URLSearchParams(fields)
  const res = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
    body,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`)
  return res.json() as Promise<T>
}

export const api = {
  nodes: () => getJSON<{ nodes: NodeInfo[] }>("/api/nodes"),
  dashboard: () => getJSON<{ dashboard: Dashboard | null; nodes: NodeInfo[] }>("/api/dashboard"),
  jobs: (node: number, page = 1, perPage = 100) =>
    getJSON<JobsResponse>(`/api/${node}/jobs/?page=${page}&per_page=${perPage}`),
  tasks: (node: number, page = 1, perPage = 100) =>
    getJSON<TasksResponse>(`/api/${node}/tasks/?page=${page}&per_page=${perPage}`),
  taskResults: (node: number, taskId: number) =>
    getJSON<TaskResultsResponse>(`/api/${node}/tasks/${taskId}/results/`),
  logText: (node: number, project: string, spider: string, job: string, finished = false) =>
    getJSON<LogTextResponse>(
      `/api/${node}/log/utf8/${encodeURIComponent(project)}/${encodeURIComponent(spider)}/${encodeURIComponent(job)}/${finished ? "?job_finished=True" : ""}`,
    ),
  logStats: (node: number, project: string, spider: string, job: string, finished = false) =>
    getJSON<LogStatsResponse>(
      `/api/${node}/log/stats/${encodeURIComponent(project)}/${encodeURIComponent(spider)}/${encodeURIComponent(job)}/${finished ? "?job_finished=True" : ""}`,
    ),
  search: (node: number, q: string) =>
    getJSON<{ results: SearchResult[] }>(`/api/${node}/search/?q=${encodeURIComponent(q)}`),
  daemonstatus: (node: number) =>
    getJSON<{ status: string; pending: number; running: number; finished: number; node_name: string }>(
      `/${node}/api/daemonstatus/`,
    ),
  authMe: () => getJSON<AuthMe>("/api/auth/me"),
  login: (username: string, password: string) =>
    postJSONBody<{ status: string; message?: string }>("/api/auth/login", { username, password }),
  setup: (username: string, password: string) =>
    postJSONBody<{ status: string; message?: string }>("/api/auth/setup", { username, password }),
  logout: () => postJSONBody<{ status: string }>("/api/auth/logout", {}),
  changePassword: (current: string, next: string) =>
    postJSONBody<{ status: string; message?: string }>("/api/auth/password", {
      current,
      new: next,
    }),
  testAlert: (channel: "slack" | "telegram" | "email") =>
    postJSONBody<{ status: string; result: Record<string, unknown> }>("/api/alerts/test", {
      channel,
    }),
  deployGit: (body: Record<string, unknown>) =>
    postJSONBody<Record<string, unknown>>("/api/deploy/git", body),
  deployHistory: (params: { page?: number; perPage?: number; project?: string; repoId?: number } = {}) => {
    const qs = new URLSearchParams()
    if (params.page) qs.set("page", String(params.page))
    if (params.perPage) qs.set("per_page", String(params.perPage))
    if (params.project) qs.set("project", params.project)
    if (params.repoId) qs.set("repo_id", String(params.repoId))
    const q = qs.toString()
    return getJSON<{ status: string; total: number; records: DeployRecord[] }>(
      `/api/deploy/history${q ? `?${q}` : ""}`,
    )
  },
  listProjects: () => getJSON<{ status: string; projects: Project[] }>("/api/projects"),
  createProject: (body: Record<string, unknown>) =>
    postJSONBody<{ status: string; message?: string; project?: Project }>("/api/projects", body),
  updateProject: (id: number, body: Record<string, unknown>) =>
    putJSON<{ status: string; message?: string; project?: Project }>(`/api/projects/${id}`, body),
  deleteProject: (id: number) =>
    deleteJSON<{ status: string; message?: string }>(`/api/projects/${id}`),
  deployProject: (id: number) =>
    postJSONBody<Record<string, unknown>>(`/api/projects/${id}/deploy`, {}),
  alertRules: () => getJSON<{ status: string; rules: AlertRule[] }>("/api/alerts/rules"),
  createAlertRule: (body: Record<string, unknown>) =>
    postJSONBody<{ status: string; message?: string; rule?: AlertRule }>("/api/alerts/rules", body),
  updateAlertRule: (id: number, body: Record<string, unknown>) =>
    putJSON<{ status: string; message?: string; rule?: AlertRule }>(`/api/alerts/rules/${id}`, body),
  deleteAlertRule: (id: number) =>
    deleteJSON<{ status: string; message?: string }>(`/api/alerts/rules/${id}`),
  codeList: (project: string, version: string) =>
    getJSON<{ status: string; message?: string; files?: { path: string; size: number }[] }>(
      `/api/code/${encodeURIComponent(project)}/${encodeURIComponent(version)}/`,
    ),
  codeFile: (project: string, version: string, path: string) =>
    getJSON<{ status: string; message?: string; text?: string }>(
      `/api/code/${encodeURIComponent(project)}/${encodeURIComponent(version)}/file?path=${encodeURIComponent(path)}`,
    ),
  settingsSchema: () => getJSON<SettingsSchemaResponse>("/api/settings/schema"),
  saveSettings: (settings: Record<string, unknown>, reset?: string[]) =>
    putJSON<SaveSettingsResponse>("/api/settings", { settings, reset: reset ?? [] }),
  // legacy JSON action endpoints (kept until cutover)
  scrapyd: (node: number, opt: string, project?: string, vsj?: string) => {
    let url = `/${node}/api/${opt}/`
    if (project) url += `${encodeURIComponent(project)}/`
    if (vsj) url += `${encodeURIComponent(vsj)}/`
    return postJSON<Record<string, unknown>>(url)
  },
  listTokens: () => getJSON<{ status: string; tokens: ApiToken[] }>("/api/tokens"),
  createToken: (name: string) =>
    postJSONBody<{ status: string; message?: string; plaintext?: string; token?: ApiToken }>(
      "/api/tokens",
      { name },
    ),
  deleteToken: (id: number) =>
    deleteJSON<{ status: string; message?: string }>(`/api/tokens/${id}`),
  listGroups: () => getJSON<{ status: string; groups: JobGroup[] }>("/api/groups"),
  createGroup: (body: Record<string, unknown>) =>
    postJSONBody<{ status: string; message?: string; group?: JobGroup }>("/api/groups", body),
  updateGroup: (id: number, body: Record<string, unknown>) =>
    putJSON<{ status: string; message?: string; group?: JobGroup }>(`/api/groups/${id}`, body),
  deleteGroup: (id: number) =>
    deleteJSON<{ status: string; message?: string }>(`/api/groups/${id}`),
  scheduleSavedGroup: (id: number, body: Record<string, unknown>) =>
    postJSONBody<{ status: string; scheduled: number; total: number; results: unknown[] }>(
      `/api/groups/${id}/schedule`,
      body,
    ),
  fireGroup: (id: number, body: Record<string, unknown> = {}) =>
    postJSONBody<{
      status: string
      scheduled: number
      total: number
      results: { node?: number; spider: string; status: string; jobid?: string; message?: string }[]
    }>(`/api/groups/${id}/fire`, body),
  scheduleGroup: (node: number, body: Record<string, unknown>) =>
    postJSONBody<{
      status: string
      scheduled: number
      total: number
      mode?: string
      results: {
        node?: number
        spider: string
        status: string
        jobid?: string
        task_id?: number
        message?: string
      }[]
    }>(`/${node}/schedule/group/`, body),
  taskAction: (node: number, action: string, taskId?: number) =>
    postJSON<Record<string, unknown>>(
      taskId != null ? `/${node}/tasks/xhr/${action}/${taskId}/` : `/${node}/tasks/xhr/${action}/`,
    ),
}
