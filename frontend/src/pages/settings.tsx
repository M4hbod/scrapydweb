import * as React from "react"
import { useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Plus, RotateCcw, Save, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import {
  api,
  type ServerRowDto,
  type SettingFieldDto,
  type SettingsSchemaResponse,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const SECRET = "__secret__"

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ["settings-schema"],
    queryFn: api.settingsSchema,
  })

  const [draft, setDraft] = React.useState<Record<string, unknown>>({})
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const dirty = Object.keys(draft).length

  const [params, setParams] = useSearchParams()
  const firstGroup = data?.groups[0]?.id ?? "servers"
  const requestedTab = params.get("tab")
  const tab =
    requestedTab && (requestedTab === "__system" || data?.groups.some((g) => g.id === requestedTab))
      ? requestedTab
      : firstGroup
  const setTab = (t: string) => {
    const next = new URLSearchParams(params)
    if (t === firstGroup) next.delete("tab")
    else next.set("tab", t)
    setParams(next, { replace: true })
  }

  const save = useMutation({
    mutationFn: () => api.saveSettings(draft),
    onSuccess: (res) => {
      if (res.status === "ok") {
        const restart = res.restart_required
        toast.success(restart ? "Saved — some changes need a restart" : "Settings saved")
        setDraft({})
        setErrors({})
        qc.invalidateQueries({ queryKey: ["settings-schema"] })
        if (res.nodes_changed) qc.invalidateQueries({ queryKey: ["nodes"] })
      } else {
        setErrors(res.errors ?? {})
        toast.error("Some settings are invalid")
      }
    },
    onError: (e) => toast.error(`Save failed: ${e.message}`),
  })

  const reset = useMutation({
    mutationFn: (key: string) => api.saveSettings({}, [key]),
    onSuccess: () => {
      toast.success("Reset to default")
      qc.invalidateQueries({ queryKey: ["settings-schema"] })
    },
  })

  if (isLoading || !data)
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )

  const setValue = (key: string, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }))
    setErrors((e) => {
      if (!e[key]) return e
      const next = { ...e }
      delete next[key]
      return next
    })
  }
  const clearValue = (key: string) =>
    setDraft((d) => {
      const next = { ...d }
      delete next[key]
      return next
    })

  const activeGroup = data.groups.find((g) => g.id === tab)
  const dirtyByGroup: Record<string, number> = {}
  for (const g of data.groups) {
    dirtyByGroup[g.id] = g.fields.filter((f) => f.key in draft).length
  }
  const errorByGroup: Record<string, number> = {}
  for (const g of data.groups) {
    errorByGroup[g.id] = g.fields.filter((f) => errors[f.key]).length
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 pb-20">
      <div className="flex items-baseline gap-3">
        <h2 className="text-lg font-semibold">Settings</h2>
        <span className="font-mono text-xs text-muted-foreground">
          stored in the database · applied live where possible
        </span>
      </div>

      {data.pending_restart.length > 0 && (
        <div className="flex items-start gap-2.5 rounded-lg border border-chart-3/40 bg-chart-3/10 px-3 py-2.5 text-sm text-chart-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            Saved but waiting for a restart:{" "}
            <span className="font-mono text-xs">{data.pending_restart.join(", ")}</span>
          </span>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-[13rem_1fr]">
        {/* group navigation */}
        <nav className="flex h-fit flex-row flex-wrap gap-1 md:sticky md:top-20 md:flex-col">
          {[...data.groups.map((g) => ({ id: g.id, label: g.label })),
            { id: "__system", label: "System info" }].map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => setTab(g.id)}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                tab === g.id
                  ? "bg-secondary font-medium text-foreground"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
              )}
            >
              <span className="truncate">{g.label}</span>
              {(errorByGroup[g.id] ?? 0) > 0 ? (
                <span className="ml-auto size-2 shrink-0 rounded-full bg-destructive" />
              ) : (dirtyByGroup[g.id] ?? 0) > 0 ? (
                <span className="ml-auto shrink-0 rounded-full bg-primary/15 px-1.5 font-mono text-[10px] text-primary">
                  {dirtyByGroup[g.id]}
                </span>
              ) : null}
            </button>
          ))}
        </nav>

        {/* active group */}
        <div className="min-w-0">
          {tab === "__system" ? (
            <SystemInfoCard info={data.system_info} />
          ) : activeGroup ? (
            <Card className="gap-3">
              <CardHeader>
                <CardTitle className="text-sm font-semibold">{activeGroup.label}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col divide-y divide-border/60">
                {activeGroup.id === "servers" && (
                  <ServersEditor
                    rows={(draft["SCRAPYD_SERVERS"] as ServerRowDto[]) ?? data.servers_value}
                    dirty={"SCRAPYD_SERVERS" in draft}
                    error={errors["SCRAPYD_SERVERS"]}
                    onChange={(rows) => setValue("SCRAPYD_SERVERS", rows)}
                  />
                )}
                {activeGroup.id === "sendtext" && <AlertTestRow />}
                {activeGroup.id === "monitor" ? (
                  <MonitorFields
                    fields={activeGroup.fields}
                    draft={draft}
                    errors={errors}
                    setValue={setValue}
                    clearValue={clearValue}
                    onReset={(k) => reset.mutate(k)}
                  />
                ) : (
                  activeGroup.fields
                    .filter((f) => f.type !== "servers")
                    .map((f) => (
                      <FieldRow
                        key={f.key}
                        field={f}
                        draftValue={draft[f.key]}
                        isDirty={f.key in draft}
                        error={errors[f.key]}
                        onChange={(v) => setValue(f.key, v)}
                        onClear={() => clearValue(f.key)}
                        onReset={() => reset.mutate(f.key)}
                      />
                    ))
                )}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>

      {dirty > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/90 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
            <span className="text-sm">
              <span className="font-mono font-semibold">{dirty}</span> unsaved change
              {dirty > 1 ? "s" : ""}
            </span>
            <Button
              size="sm"
              className="ml-auto gap-1.5"
              disabled={save.isPending}
              onClick={() => save.mutate()}
            >
              <Save className="size-3.5" /> {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setDraft({})
                setErrors({})
              }}
            >
              Discard
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

const TRIGGER_KINDS = ["CRITICAL", "ERROR", "WARNING", "REDIRECT", "RETRY", "IGNORE"]

function AlertTestRow() {
  const [busy, setBusy] = React.useState<string | null>(null)
  const test = async (channel: "slack" | "telegram" | "email") => {
    setBusy(channel)
    try {
      const res = await api.testAlert(channel)
      if (res.status === "ok") toast.success(`${channel}: test message sent`)
      else toast.error(`${channel}: ${JSON.stringify(res.result).slice(0, 200)}`)
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2 py-3 first:pt-0">
      <span className="text-sm font-medium">Send a test message</span>
      <div className="ml-auto flex gap-2">
        {(["slack", "telegram", "email"] as const).map((ch) => (
          <Button
            key={ch}
            variant="outline"
            size="sm"
            className="h-7 text-xs capitalize"
            disabled={busy !== null}
            onClick={() => test(ch)}
          >
            {busy === ch ? "…" : ch}
          </Button>
        ))}
      </div>
    </div>
  )
}

function MonitorFields({
  fields,
  draft,
  errors,
  setValue,
  clearValue,
  onReset,
}: {
  fields: SettingFieldDto[]
  draft: Record<string, unknown>
  errors: Record<string, string>
  setValue: (k: string, v: unknown) => void
  clearValue: (k: string) => void
  onReset: (k: string) => void
}) {
  const byKey = Object.fromEntries(fields.map((f) => [f.key, f]))
  const plain = fields.filter((f) => !f.key.startsWith("LOG_"))
  const val = (key: string) => (key in draft ? draft[key] : byKey[key]?.value)

  return (
    <>
      {plain.map((f) => (
        <FieldRow
          key={f.key}
          field={f}
          draftValue={draft[f.key]}
          isDirty={f.key in draft}
          error={errors[f.key]}
          onChange={(v) => setValue(f.key, v)}
          onClear={() => clearValue(f.key)}
          onReset={() => onReset(f.key)}
        />
      ))}
      {/* compact alert-trigger matrix instead of 18 separate rows */}
      <div className="flex flex-col gap-2 py-3 last:pb-0">
        <span className="text-sm font-medium">Log alert triggers</span>
        <p className="text-xs text-muted-foreground">
          Alert when a log category exceeds its threshold (0 disables); optionally stop or
          force-stop the job.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full max-w-xl text-xs">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="py-1.5 pr-4 font-medium">category</th>
                <th className="py-1.5 pr-4 font-medium">threshold</th>
                <th className="py-1.5 pr-4 text-center font-medium">stop</th>
                <th className="py-1.5 text-center font-medium">force-stop</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {TRIGGER_KINDS.map((kind) => {
                const tKey = `LOG_${kind}_THRESHOLD`
                const sKey = `LOG_${kind}_TRIGGER_STOP`
                const fKey = `LOG_${kind}_TRIGGER_FORCESTOP`
                const dirtyRow = [tKey, sKey, fKey].some((k) => k in draft)
                return (
                  <tr key={kind}>
                    <td className={cn("py-1.5 pr-4 font-mono", dirtyRow && "text-primary")}>
                      {kind.toLowerCase()}
                      {dirtyRow && <span className="ml-1 text-primary">•</span>}
                    </td>
                    <td className="py-1.5 pr-4">
                      <Input
                        type="number"
                        min={0}
                        value={String(val(tKey) ?? 0)}
                        onChange={(e) =>
                          e.target.value === ""
                            ? clearValue(tKey)
                            : setValue(tKey, parseInt(e.target.value, 10))
                        }
                        className="h-7 w-24 text-right font-mono text-xs"
                      />
                    </td>
                    <td className="py-1.5 pr-4 text-center">
                      <Switch
                        checked={Boolean(val(sKey))}
                        onCheckedChange={(v) => setValue(sKey, v)}
                      />
                    </td>
                    <td className="py-1.5 text-center">
                      <Switch
                        checked={Boolean(val(fKey))}
                        onCheckedChange={(v) => setValue(fKey, v)}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {TRIGGER_KINDS.flatMap((k) =>
          [`LOG_${k}_THRESHOLD`, `LOG_${k}_TRIGGER_STOP`, `LOG_${k}_TRIGGER_FORCESTOP`],
        )
          .filter((k) => errors[k])
          .map((k) => (
            <p key={k} className="font-mono text-xs text-destructive">
              {k}: {errors[k]}
            </p>
          ))}
      </div>
    </>
  )
}

function FieldRow({
  field: f,
  draftValue,
  isDirty,
  error,
  onChange,
  onClear,
  onReset,
}: {
  field: SettingFieldDto
  draftValue: unknown
  isDirty: boolean
  error?: string
  onChange: (v: unknown) => void
  onClear: () => void
  onReset: () => void
}) {
  const value = isDirty ? draftValue : f.value
  const showReset = f.source === "db" && !isDirty

  return (
    <div className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("text-sm font-medium", isDirty && "text-primary")}>
          {f.label}
          {isDirty && <span className="ml-1 text-primary">•</span>}
        </span>
        <code className="font-mono text-[10px] text-muted-foreground/60">{f.key}</code>
        {f.source !== "default" && !isDirty && (
          <Badge variant="outline" className="h-4 px-1.5 font-mono text-[9px] uppercase">
            {f.source}
          </Badge>
        )}
        {f.apply === "restart" && (
          <Badge variant="secondary" className="h-4 px-1.5 text-[9px]">
            needs restart
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-2">
          {showReset && (
            <Button
              variant="ghost"
              size="icon"
              className="size-6 text-muted-foreground"
              title="Reset to default"
              onClick={onReset}
            >
              <RotateCcw className="size-3" />
            </Button>
          )}
          <FieldControl field={f} value={value} onChange={onChange} onClear={onClear} />
        </div>
      </div>
      {f.help && <p className="text-xs text-muted-foreground">{f.help}</p>}
      {error && <p className="font-mono text-xs text-destructive">{error}</p>}
    </div>
  )
}

function FieldControl({
  field: f,
  value,
  onChange,
  onClear,
}: {
  field: SettingFieldDto
  value: unknown
  onChange: (v: unknown) => void
  onClear: () => void
}) {
  if (f.type === "bool" && !f.nullable)
    return <Switch checked={Boolean(value)} onCheckedChange={onChange} />

  if (f.nullable && (f.type === "bool" || f.type === "enum")) {
    const opts = f.type === "bool" ? ["True", "False"] : (f.choices ?? [])
    const current = value === null || value === undefined ? "__null__" : String(value)
    return (
      <Select
        value={current}
        onValueChange={(v) =>
          onChange(v === "__null__" ? null : f.type === "bool" ? v === "True" : v)
        }
      >
        <SelectTrigger size="sm" className="w-44 font-mono text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__null__" className="text-xs">
            (spider default)
          </SelectItem>
          {opts.map((o) => (
            <SelectItem key={o} value={o} className="font-mono text-xs">
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  if (f.type === "enum")
    return (
      <Select value={String(value ?? "")} onValueChange={onChange}>
        <SelectTrigger size="sm" className="w-44 font-mono text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(f.choices ?? []).map((o) => (
            <SelectItem key={o} value={o} className="font-mono text-xs">
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )

  if (f.type === "int" || f.type === "float") {
    const empty = value === null || value === undefined || value === ""
    return (
      <Input
        type="number"
        min={f.min ?? undefined}
        step={f.type === "float" ? "any" : 1}
        value={empty ? "" : String(value)}
        placeholder={f.nullable ? "(default)" : String(f.default ?? "")}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === "") return f.nullable ? onChange(null) : onClear()
          onChange(f.type === "float" ? parseFloat(raw) : parseInt(raw, 10))
        }}
        className="h-8 w-32 text-right font-mono text-xs"
      />
    )
  }

  if (f.type === "secret") {
    const stored = f.value === SECRET
    return (
      <Input
        type="password"
        autoComplete="new-password"
        placeholder={stored ? "•••••••• (unchanged)" : "not set"}
        value={typeof value === "string" && value !== SECRET ? value : ""}
        onChange={(e) => (e.target.value === "" ? onClear() : onChange(e.target.value))}
        className="h-8 w-56 font-mono text-xs"
      />
    )
  }

  if (f.type === "list_str" || f.type === "list_int") {
    return <ListInput field={f} value={value} onChange={onChange} />
  }

  // str
  if (f.textarea)
    return (
      <Textarea
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-16 w-72 font-mono text-xs"
      />
    )
  return (
    <Input
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 w-64 font-mono text-xs"
    />
  )
}

// Comma-separated list editor. Keeps the raw text in local state while typing so a
// trailing comma / space survives keystrokes (parsing on every change would strip the
// empty segment and the comma would vanish). Emits the parsed array to the parent;
// resyncs to the normalized value when not actively editing.
function ListInput({
  field: f,
  value,
  onChange,
}: {
  field: SettingFieldDto
  value: unknown
  onChange: (v: unknown) => void
}) {
  const canonical = (Array.isArray(value) ? value : []).join(", ")
  const [text, setText] = React.useState(canonical)
  const [editing, setEditing] = React.useState(false)
  React.useEffect(() => {
    if (!editing) setText(canonical)
  }, [canonical, editing])
  return (
    <Input
      value={text}
      placeholder="comma separated"
      inputMode={f.type === "list_int" ? "numeric" : undefined}
      onFocus={() => setEditing(true)}
      onBlur={() => setEditing(false)}
      onChange={(e) => {
        setText(e.target.value)
        const parts = e.target.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
        onChange(f.type === "list_int" ? parts.map(Number) : parts)
      }}
      className="h-8 w-64 font-mono text-xs"
    />
  )
}

function ServersEditor({
  rows,
  dirty,
  error,
  onChange,
}: {
  rows: ServerRowDto[]
  dirty: boolean
  error?: string
  onChange: (rows: ServerRowDto[]) => void
}) {
  const update = (i: number, patch: Partial<ServerRowDto>) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  return (
    <div className="flex flex-col gap-2 py-3 first:pt-0">
      <div className="flex items-center gap-2">
        <span className={cn("text-sm font-medium", dirty && "text-primary")}>
          Scrapyd servers{dirty && <span className="ml-1 text-primary">•</span>}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto h-7 gap-1 text-xs"
          onClick={() =>
            onChange([
              ...rows,
              { host: "", port: 6800, username: "", password: "", group: "", public_url: "" },
            ])
          }
        >
          <Plus className="size-3" /> Add server
        </Button>
      </div>
      {error && <p className="font-mono text-xs text-destructive">{error}</p>}
      <div className="flex flex-col gap-2">
        {rows.map((r, i) => (
          <div
            key={i}
            className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-secondary/30 p-2 sm:grid-cols-[1fr_5rem_7rem_7rem_6rem_auto]"
          >
            <Input
              placeholder="host"
              value={r.host}
              onChange={(e) => update(i, { host: e.target.value })}
              className="h-8 font-mono text-xs"
            />
            <Input
              type="number"
              placeholder="port"
              value={r.port || ""}
              onChange={(e) => update(i, { port: parseInt(e.target.value || "6800", 10) })}
              className="h-8 font-mono text-xs"
            />
            <Input
              placeholder="username"
              value={r.username}
              onChange={(e) => update(i, { username: e.target.value })}
              className="h-8 font-mono text-xs"
            />
            <Input
              type="password"
              autoComplete="new-password"
              placeholder={r.password === SECRET ? "•••• (unchanged)" : "password"}
              value={r.password === SECRET ? "" : r.password}
              onChange={(e) => update(i, { password: e.target.value || SECRET })}
              className="h-8 font-mono text-xs"
            />
            <Input
              placeholder="group"
              value={r.group}
              onChange={(e) => update(i, { group: e.target.value })}
              className="h-8 font-mono text-xs"
            />
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-destructive hover:text-destructive"
              title="Remove server"
              onClick={() => onChange(rows.filter((_, idx) => idx !== i))}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Changes here re-derive the node list — open pages refresh automatically.
      </p>
    </div>
  )
}

function SystemInfoCard({ info }: { info: SettingsSchemaResponse["system_info"] }) {
  const entries = Object.entries(info).filter(([k]) => k !== "databases")
  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle className="text-sm font-semibold">System info (read-only)</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 font-mono text-xs">
          {entries.map(([k, v]) => (
            <React.Fragment key={k}>
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="truncate">{String(v ?? "–")}</dd>
            </React.Fragment>
          ))}
          {Object.entries(info.databases ?? {}).map(([k, v]) => (
            <React.Fragment key={k}>
              <dt className="text-muted-foreground">db.{k}</dt>
              <dd className="truncate">{v}</dd>
            </React.Fragment>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
