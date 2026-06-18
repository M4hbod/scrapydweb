import { useFormContext, useWatch } from "react-hook-form"
import { useQuery } from "@tanstack/react-query"
import { CalendarClock, ChevronDown, Play, TerminalSquare } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Separator } from "@/components/ui/separator"
import { useCronPreview } from "./cron-preview"
import { api } from "@/lib/api"
import {
  LATEST,
  backendGroupCurl,
  sanitizeJobid,
  type ScheduleFormValues,
} from "@/lib/schedule-payload"

export function SummaryPanel({ pending }: { pending: boolean }) {
  const form = useFormContext<ScheduleFormValues>()
  const v = useWatch({ control: form.control }) as ScheduleFormValues
  const { data: nodesData } = useQuery({ queryKey: ["nodes"], queryFn: api.nodes, staleTime: 60_000 })

  const allNodes = nodesData?.nodes ?? []
  const selected = allNodes.filter((n) => (v.nodes ?? []).includes(n.node))
  const settings = (v.settings ?? []).filter((s) => s.key && s.value)
  const args = (v.args ?? []).filter((a) => a.key && a.value)
  const cron = v.mode === "cron"

  const { data: cronData } = useCronPreview(
    {
      minute: v.minute ?? "0",
      hour: v.hour ?? "*",
      day: v.day ?? "*",
      month: v.month ?? "*",
      day_of_week: v.day_of_week ?? "*",
      second: v.second ?? "0",
      week: v.week ?? "*",
      year: v.year ?? "*",
    },
    cron,
  )

  const issues = Object.keys(form.formState.errors).length

  // the same scrapydweb request the page submits, recreating this exact job/task
  const curlNode = v.nodes?.[0] ?? 1
  const curlBody: Record<string, unknown> = {
    project: v.project || "",
    _version: v._version || LATEST,
    spiders: v.spider ? [v.spider] : [],
    nodes: v.nodes ?? [],
    jobid: v.jobid || "",
    settings,
    args: Object.fromEntries(args.map((a) => [a.key, a.value])),
  }
  if (cron)
    Object.assign(curlBody, {
      trigger: "cron",
      action: v.action,
      name: v.name,
      year: v.year,
      month: v.month,
      day: v.day,
      week: v.week,
      day_of_week: v.day_of_week,
      hour: v.hour,
      minute: v.minute,
      second: v.second,
    })

  return (
    <Card className="gap-3 lg:sticky lg:top-20 lg:self-start">
      <CardHeader>
        <CardTitle className="text-sm font-semibold">Summary</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="flex flex-col gap-1 font-mono text-xs">
          <Row label="project" value={v.project || "—"} />
          <Row
            label="version"
            value={!v._version || v._version === LATEST ? "latest" : v._version}
          />
          <Row label="spider" value={v.spider || "—"} />
          <Row label="jobid" value={v.jobid ? sanitizeJobid(v.jobid) : "auto"} />
        </div>

        <Separator />

        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            nodes ({selected.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {selected.length === 0 && <span className="text-xs text-destructive">none selected</span>}
            {selected.map((n) => (
              <Badge key={n.node} variant="secondary" className="font-mono text-[10px]">
                {n.node} · {n.server}
              </Badge>
            ))}
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            settings ({settings.length})
          </p>
          {settings.length === 0 ? (
            <p className="text-xs text-muted-foreground">project defaults</p>
          ) : (
            <div className="flex flex-col gap-0.5 font-mono text-[11px]">
              {settings.map((s) => (
                <span key={s.key} className="truncate">
                  <span className="text-primary">{s.key}</span>=
                  <span className="text-foreground/80">{s.value}</span>
                </span>
              ))}
            </div>
          )}
        </div>

        {args.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              arguments ({args.length})
            </p>
            <div className="flex flex-col gap-0.5 font-mono text-[11px]">
              {args.map((a) => (
                <span key={a.key} className="truncate">
                  <span className="text-chart-3">{a.key}</span>=
                  <span className="text-foreground/80">{a.value}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        <Separator />

        <div className="flex items-start gap-2 text-xs">
          <CalendarClock className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          {cron ? (
            <div className="min-w-0 font-mono">
              <p>
                cron {v.minute} {v.hour} {v.day} {v.month} {v.day_of_week}
              </p>
              {cronData?.status === "ok" &&
                (cronData.next_runs?.length ? (
                  <p className="truncate text-primary">next: {cronData.next_runs[0]}</p>
                ) : (
                  <p className="text-chart-3">never fires</p>
                ))}
            </div>
          ) : (
            <p className="font-mono">runs immediately</p>
          )}
        </div>

        <Collapsible>
          <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <TerminalSquare className="size-3.5" /> Equivalent curl
            <ChevronDown className="size-3" />
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2">
            <pre className="overflow-auto rounded-lg bg-background/70 p-2.5 font-mono text-[11px] leading-relaxed">
              {backendGroupCurl(curlNode, curlBody, window.location.origin)}
            </pre>
            <p className="mt-1 text-[10px] text-muted-foreground">
              hits the scrapydweb backend; log in first (POST /api/auth/login) and pass the session cookie
            </p>
          </CollapsibleContent>
        </Collapsible>

        <Button type="submit" disabled={pending} className="w-full">
          <Play className="size-4" /> {cron ? "Save task" : "Run spider"}
        </Button>
        {issues > 0 && (
          <p className="text-center text-xs text-destructive">
            {issues} field{issues > 1 ? "s" : ""} need attention
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate">{value}</span>
    </span>
  )
}
