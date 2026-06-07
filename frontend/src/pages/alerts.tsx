import * as React from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bell, Pencil, Plus, Send, Trash2, TriangleAlert } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { useConfirm } from "@/components/confirm-dialog"
import { api, type AlertRule, type AlertThresholdSpec } from "@/lib/api"

const KINDS = ["CRITICAL", "ERROR", "WARNING", "REDIRECT", "RETRY", "IGNORE"] as const
const CHANNELS = ["slack", "telegram", "email"] as const
const ACTION_LABEL: Record<string, string> = {
  alert: "alert only",
  stop: "alert + stop",
  forcestop: "alert + force-stop",
}

export default function AlertsPage() {
  const qc = useQueryClient()
  const { confirm: confirmDialog, dialog: confirmUI } = useConfirm()
  const { data, isLoading } = useQuery({ queryKey: ["alert-rules"], queryFn: api.alertRules })
  const [editing, setEditing] = React.useState<AlertRule | "new" | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["alert-rules"] })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.updateAlertRule(id, { enabled }),
    onSuccess: invalidate,
    onError: (e) => toast.error(`Update failed: ${e.message}`),
  })

  const del = useMutation({
    mutationFn: (id: number) => api.deleteAlertRule(id),
    onSuccess: (res) => {
      if (res.status === "ok") toast.success("Rule deleted")
      else toast.error(res.message ?? "Delete failed")
      invalidate()
    },
    onError: (e) => toast.error(`Delete failed: ${e.message}`),
  })

  const rules = data?.rules ?? []
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Alerts</h2>
        <span className="font-mono text-xs text-muted-foreground">
          {rules.length} rule{rules.length === 1 ? "" : "s"}
        </span>
        <Button size="sm" className="ml-auto h-8 gap-1.5 text-xs" onClick={() => setEditing("new")}>
          <Plus className="size-3.5" /> Add rule
        </Button>
      </div>

      <WorkingTimeBanner />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Rules</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            A rule overrides the global alert settings for matching jobs (glob patterns,
            most-specific match wins per field). Global defaults live in{" "}
            <Link to="/settings" className="text-primary hover:underline">
              Settings → Alerts
            </Link>
            . Alerts are evaluated by the stats collector — no spider code changes needed.
          </p>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {isLoading && <Skeleton className="h-24 rounded-lg" />}
          {!isLoading && rules.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No rules yet — the global settings apply to every job.
            </p>
          )}
          {rules.map((r) => (
            <div
              key={r.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-secondary/30 px-3 py-2.5"
            >
              <Bell className="size-4 text-muted-foreground" />
              <span className="font-medium">{r.name}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {r.project_pattern}/{r.spider_pattern}
              </span>
              {Object.entries(r.thresholds ?? {}).map(([kind, spec]) => (
                <Badge
                  key={kind}
                  variant={spec.action ? "destructive" : "secondary"}
                  className="font-mono text-[10px]"
                  title={ACTION_LABEL[spec.action ?? "alert"]}
                >
                  {kind} ≥ {spec.threshold}
                  {spec.action === "stop" ? " ■" : spec.action === "forcestop" ? " ■■" : ""}
                </Badge>
              ))}
              {r.on_finished != null && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  finish: {r.on_finished ? "on" : "off"}
                </Badge>
              )}
              {r.on_running_interval != null && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  every {r.on_running_interval}s
                </Badge>
              )}
              {r.channels && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  → {r.channels.join(",")}
                </Badge>
              )}
              <div className="ml-auto flex items-center gap-1.5">
                <Switch
                  checked={r.enabled}
                  onCheckedChange={(enabled) => toggle.mutate({ id: r.id, enabled })}
                  aria-label={`Enable ${r.name}`}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  aria-label={`Edit ${r.name}`}
                  onClick={() => setEditing(r)}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7 text-destructive hover:text-destructive"
                  aria-label={`Delete ${r.name}`}
                  onClick={async () =>
                    (await confirmDialog({
                      title: `Delete rule "${r.name}"?`,
                      description: "Matching jobs fall back to the global alert settings.",
                      confirmLabel: "Delete rule",
                      destructive: true,
                    })) && del.mutate(r.id)
                  }
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <ChannelTestCard />

      {editing && (
        <RuleDialog
          rule={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      )}
      {confirmUI}
    </div>
  )
}

function WorkingTimeBanner() {
  const { data } = useQuery({ queryKey: ["settings-schema"], queryFn: api.settingsSchema })
  const monitor = data?.groups.find((g) => g.id === "monitor")
  if (!monitor) return null
  const val = (key: string) => monitor.fields.find((f) => f.key === key)?.value
  const channelOn = CHANNELS.some((c) => val(`ENABLE_${c.toUpperCase()}_ALERT`) === true)
  const days = (val("ALERT_WORKING_DAYS") as number[] | undefined) ?? []
  const hours = (val("ALERT_WORKING_HOURS") as number[] | undefined) ?? []
  if (!channelOn || (days.length > 0 && hours.length > 0)) return null
  return (
    <Card className="border-chart-3/50 bg-chart-3/10">
      <CardContent className="flex items-center gap-3 py-3 text-sm">
      <TriangleAlert className="size-4 shrink-0 text-chart-3" />
        <span>
          Alert channels are enabled but{" "}
          <span className="font-mono text-xs">
            {days.length === 0 ? "working days" : "working hours"}
          </span>{" "}
          is empty — <strong>no notification will ever be sent</strong>. Set both in{" "}
          <Link to="/settings" className="text-primary hover:underline">
            Settings → Alerts
          </Link>
          .
        </span>
      </CardContent>
    </Card>
  )
}

function ChannelTestCard() {
  const [busy, setBusy] = React.useState<string | null>(null)
  const test = async (channel: (typeof CHANNELS)[number]) => {
    setBusy(channel)
    try {
      const res = await api.testAlert(channel)
      if (res.status === "ok") toast.success(`${channel} works`)
      else toast.error(`${channel}: ${JSON.stringify(res.result).slice(0, 200)}`)
    } catch (e) {
      toast.error(`${channel}: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold">Channels</CardTitle>
        <p className="mt-1 text-xs text-muted-foreground">
          Tokens / SMTP are configured in Settings → Slack / Telegram / Email. Send a test message:
        </p>
      </CardHeader>
      <CardContent className="flex gap-2">
        {CHANNELS.map((c) => (
          <Button
            key={c}
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs capitalize"
            disabled={busy != null}
            onClick={() => test(c)}
          >
            <Send className="size-3" /> {busy === c ? "Sending…" : c}
          </Button>
        ))}
      </CardContent>
    </Card>
  )
}

interface ThresholdRow {
  threshold: string // input value; "" = inherit global
  action: "alert" | "stop" | "forcestop"
}

function RuleDialog({
  rule,
  onClose,
  onSaved,
}: {
  rule: AlertRule | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = React.useState(rule?.name ?? "")
  const [projectPattern, setProjectPattern] = React.useState(rule?.project_pattern ?? "*")
  const [spiderPattern, setSpiderPattern] = React.useState(rule?.spider_pattern ?? "*")
  const [thresholds, setThresholds] = React.useState<Record<string, ThresholdRow>>(() => {
    const out: Record<string, ThresholdRow> = {}
    for (const k of KINDS) {
      const spec: AlertThresholdSpec | undefined = rule?.thresholds?.[k]
      out[k] = spec
        ? { threshold: String(spec.threshold), action: spec.action ?? "alert" }
        : { threshold: "", action: "alert" }
    }
    return out
  })
  const [onFinished, setOnFinished] = React.useState<"inherit" | "on" | "off">(
    rule?.on_finished == null ? "inherit" : rule.on_finished ? "on" : "off",
  )
  const [interval, setInterval_] = React.useState(
    rule?.on_running_interval != null ? String(rule.on_running_interval) : "",
  )
  const [channelMode, setChannelMode] = React.useState<"inherit" | "override">(
    rule?.channels ? "override" : "inherit",
  )
  const [channels, setChannels] = React.useState<string[]>(rule?.channels ?? [])
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const setRow = (kind: string, patch: Partial<ThresholdRow>) =>
    setThresholds((t) => ({ ...t, [kind]: { ...t[kind], ...patch } }))

  const save = async () => {
    setError("")
    setBusy(true)
    try {
      const ths: Record<string, { threshold: number; action: string | null }> = {}
      for (const k of KINDS) {
        const row = thresholds[k]
        if (row.threshold.trim() === "") continue
        const n = Number(row.threshold)
        if (!Number.isInteger(n) || n < 0) {
          setError(`${k} threshold must be an integer ≥ 0`)
          setBusy(false)
          return
        }
        if (n > 0) ths[k] = { threshold: n, action: row.action === "alert" ? null : row.action }
      }
      const body: Record<string, unknown> = {
        name,
        project_pattern: projectPattern,
        spider_pattern: spiderPattern,
        thresholds: ths,
        on_finished: onFinished === "inherit" ? null : onFinished === "on",
        on_running_interval: interval.trim() === "" ? null : Number(interval),
        channels: channelMode === "inherit" ? null : channels,
      }
      const res = rule ? await api.updateAlertRule(rule.id, body) : await api.createAlertRule(body)
      if (res.status === "ok") {
        toast.success(rule ? "Rule updated" : "Rule created")
        onSaved()
        onClose()
      } else {
        setError(res.message ?? "Save failed")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{rule ? `Edit ${rule.name}` : "New alert rule"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="grid gap-2">
              <Label htmlFor="ar-name">Name</Label>
              <Input id="ar-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ar-project">Project pattern</Label>
              <Input id="ar-project" className="font-mono text-xs" value={projectPattern}
                     onChange={(e) => setProjectPattern(e.target.value)} placeholder="* or demo*" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ar-spider">Spider pattern</Label>
              <Input id="ar-spider" className="font-mono text-xs" value={spiderPattern}
                     onChange={(e) => setSpiderPattern(e.target.value)} placeholder="*" />
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Log thresholds (empty = inherit global)</Label>
            <div className="flex flex-col gap-1.5 rounded-lg border border-border p-3">
              {KINDS.map((k) => (
                <div key={k} className="flex items-center gap-2">
                  <span className="w-24 font-mono text-xs">{k}</span>
                  <Input
                    type="number"
                    min={0}
                    placeholder="inherit"
                    className="h-7 w-24 font-mono text-xs"
                    value={thresholds[k].threshold}
                    onChange={(e) => setRow(k, { threshold: e.target.value })}
                  />
                  <Select
                    value={thresholds[k].action}
                    onValueChange={(v) => setRow(k, { action: v as ThresholdRow["action"] })}
                  >
                    <SelectTrigger size="sm" className="h-7 w-44 text-xs"
                                   disabled={thresholds[k].threshold.trim() === ""}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(ACTION_LABEL).map(([v, label]) => (
                        <SelectItem key={v} value={v} className="text-xs">
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>Alert when job finishes</Label>
              <Select value={onFinished} onValueChange={(v) => setOnFinished(v as typeof onFinished)}>
                <SelectTrigger size="sm" className="text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inherit" className="text-xs">inherit global</SelectItem>
                  <SelectItem value="on" className="text-xs">on</SelectItem>
                  <SelectItem value="off" className="text-xs">off</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ar-interval">Alert while running every (s)</Label>
              <Input id="ar-interval" type="number" min={0} placeholder="inherit"
                     className="font-mono text-xs" value={interval}
                     onChange={(e) => setInterval_(e.target.value)} />
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Channels</Label>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={channelMode}
                      onValueChange={(v) => setChannelMode(v as typeof channelMode)}>
                <SelectTrigger size="sm" className="w-36 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inherit" className="text-xs">inherit global</SelectItem>
                  <SelectItem value="override" className="text-xs">override</SelectItem>
                </SelectContent>
              </Select>
              {channelMode === "override" &&
                CHANNELS.map((c) => {
                  const active = channels.includes(c)
                  return (
                    <button
                      key={c}
                      type="button"
                      onClick={() =>
                        setChannels((cur) =>
                          active ? cur.filter((x) => x !== c) : [...cur, c],
                        )
                      }
                      className={
                        active
                          ? "rounded-full border border-primary/60 bg-primary/15 px-3 py-1 font-mono text-xs text-primary"
                          : "rounded-full border border-border bg-secondary/40 px-3 py-1 font-mono text-xs text-muted-foreground hover:border-primary/30"
                      }
                    >
                      {c}
                    </button>
                  )
                })}
            </div>
          </div>

          {error && <p className="font-mono text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy || !name} onClick={save}>
            {busy ? "Saving…" : rule ? "Save changes" : "Create rule"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
