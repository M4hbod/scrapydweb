import * as React from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowDownToLine, Code2, Download, ExternalLink } from "lucide-react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { StatusPill } from "@/components/status-pill"
import { api, type LogStatsResponse, type LogTextResponse } from "@/lib/api"
import { fmtDateTime } from "@/lib/datetime"

export default function LogPage() {
  const { node: nodeParam, opt, project, spider, job } = useParams()
  const node = Number(nodeParam)
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const finished = params.get("finished") === "1"
  const mode = opt === "stats" ? "stats" : "utf8"
  const qs = finished ? "?finished=1" : ""

  const setMode = (m: string) =>
    navigate(`/log/${node}/${m}/${project}/${spider}/${job}${qs}`, { replace: true })

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">{spider}</h2>
        <span className="font-mono text-xs text-muted-foreground">
          {project} · {job} · node {node}
        </span>
        <Tabs value={mode} className="ml-auto">
          <TabsList>
            <TabsTrigger value="stats" onClick={() => mode !== "stats" && setMode("stats")}>
              Stats
            </TabsTrigger>
            <TabsTrigger value="utf8" onClick={() => mode !== "utf8" && setMode("utf8")}>
              Log
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      {mode === "utf8" ? (
        <LogText node={node} project={project!} spider={spider!} job={job!} known={finished} />
      ) : (
        <LogStats node={node} project={project!} spider={spider!} job={job!} known={finished} />
      )}
    </div>
  )
}

function LogText({
  node,
  project,
  spider,
  job,
  known,
}: {
  node: number
  project: string
  spider: string
  job: string
  known: boolean
}) {
  const [follow, setFollow] = React.useState(true)
  const panelRef = React.useRef<HTMLPreElement>(null)

  const { data, isLoading } = useQuery<LogTextResponse>({
    queryKey: ["log-utf8", node, project, spider, job, known],
    queryFn: () => api.logText(node, project, spider, job, known),
    refetchInterval: (q) => (q.state.data?.finished ? false : 5_000),
  })

  React.useEffect(() => {
    if (follow && panelRef.current) panelRef.current.scrollTop = panelRef.current.scrollHeight
  }, [data?.text, follow])

  if (isLoading) return <Skeleton className="h-[70vh] rounded-xl" />
  if (!data || data.status !== "ok")
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-destructive">
          Failed to load log ({data?.status_code ?? "?"}).
        </CardContent>
      </Card>
    )

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row items-center gap-3 border-b border-border !py-3">
        <StatusPill
          status={data.finished ? "fin" : "run"}
          label={data.finished ? "FINISHED" : "LIVE"}
        />
        <span className="font-mono text-xs text-muted-foreground">
          {data.text.split("\n").length.toLocaleString()} lines
        </span>
        <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <ArrowDownToLine className="size-3.5" />
          Follow tail
          <Switch checked={follow} onCheckedChange={setFollow} />
        </label>
        {data.version && (
          <Button variant="outline" size="sm" asChild className="h-7 gap-1.5 text-xs">
            <Link
              to={`/code/${encodeURIComponent(project)}/${encodeURIComponent(data.version)}`}
              title={`View code (${data.version})`}
            >
              <Code2 className="size-3" /> Code
            </Link>
          </Button>
        )}
        {data.url_source && (
          <Button variant="outline" size="sm" asChild className="h-7 gap-1.5 text-xs">
            <a
              href={`/api/${node}/download/logs/${encodeURIComponent(project)}/${encodeURIComponent(spider)}/${encodeURIComponent(data.url_source.split("/").pop()!)}`}
            >
              <Download className="size-3" /> Download
            </a>
          </Button>
        )}
      </CardHeader>
      <CardContent className="px-0">
        <pre
          ref={panelRef}
          className="h-[68vh] overflow-auto whitespace-pre-wrap break-all px-4 py-3 font-mono text-xs leading-relaxed text-foreground/90"
        >
          {data.text ? <ColoredLog text={data.text} /> : "(empty log)"}
        </pre>
      </CardContent>
    </Card>
  )
}

// scrapy log line: `2026-06-06 16:01:58 [scrapy.core.engine] INFO: message`
const LOG_LINE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?) \[([^\]]+)\] (DEBUG|INFO|WARNING|ERROR|CRITICAL): ?(.*)$/

const LEVEL_STYLES: Record<string, { badge: string; msg?: string }> = {
  DEBUG: { badge: "text-muted-foreground" },
  INFO: { badge: "text-chart-2" },
  WARNING: { badge: "text-chart-3", msg: "text-chart-3/90" },
  ERROR: { badge: "text-destructive", msg: "text-destructive/90" },
  CRITICAL: { badge: "bg-destructive/20 text-destructive font-bold", msg: "text-destructive" },
}

const ColoredLog = React.memo(function ColoredLog({ text }: { text: string }) {
  const lines = text.split("\n")
  let lastLevel = ""
  return (
    <>
      {lines.map((line, i) => {
        const m = LOG_LINE.exec(line)
        if (m) {
          const [, ts, logger, level, msg] = m
          lastLevel = level
          const s = LEVEL_STYLES[level]
          return (
            <span key={i} className="block">
              <span className="text-muted-foreground/60">{ts}</span>{" "}
              <span className="text-chart-4">[{logger}]</span>{" "}
              <span className={s.badge}>{level}:</span>{" "}
              <span className={s.msg}>{msg}</span>
            </span>
          )
        }
        // continuation lines (tracebacks, stats dicts) inherit context
        const traceback =
          lastLevel === "ERROR" ||
          lastLevel === "CRITICAL" ||
          /^Traceback \(most recent call last\)/.test(line)
        return (
          <span
            key={i}
            className={traceback ? "block text-destructive/80" : "block text-foreground/70"}
          >
            {line}
          </span>
        )
      })}
    </>
  )
})

function LogStats({
  node,
  project,
  spider,
  job,
  known,
}: {
  node: number
  project: string
  spider: string
  job: string
  known: boolean
}) {
  const { data, isLoading } = useQuery<LogStatsResponse>({
    queryKey: ["log-stats", node, project, spider, job, known],
    queryFn: () => api.logStats(node, project, spider, job, known),
    refetchInterval: (q) => (q.state.data?.finished ? false : 10_000),
  })

  if (isLoading) return <Skeleton className="h-96 rounded-xl" />
  const s = data?.stats
  if (!data || data.status !== "ok" || !s)
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-destructive">
          No stats available for this job.
        </CardContent>
      </Card>
    )

  return (
    <StatsPanel
      stats={s}
      logparserValid={data.logparser_valid}
      urlSource={data.url_source}
      footer={
        <>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/log/${node}/utf8/${project}/${spider}/${job}${known ? "?finished=1" : ""}`}>
              View log
            </Link>
          </Button>
          {data.version && (
            <Button variant="outline" size="sm" asChild>
              <Link
                to={`/code/${encodeURIComponent(project)}/${encodeURIComponent(data.version)}`}
                title={`View code (${data.version})`}
              >
                <Code2 className="size-3" /> Code
              </Link>
            </Button>
          )}
        </>
      }
    />
  )
}

// Crawl-progress line chart over logparser's time-series:
// each datas row is [time, pages, pages/min, items, items/min].
function ProgressChart({ datas }: { datas?: [string, number, number, number, number][] }) {
  const points = React.useMemo(
    () =>
      (datas ?? []).map((d) => ({
        t: String(d[0]).slice(11, 19) || String(d[0]),
        pages: d[1],
        items: d[3],
      })),
    [datas],
  )
  if (points.length < 2) return null

  return (
    <Card className="gap-2 py-4">
      <CardHeader className="py-0">
        <CardTitle className="text-sm font-semibold">Crawl progress</CardTitle>
      </CardHeader>
      <CardContent className="px-2">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="t"
              tickLine={false}
              axisLine={false}
              fontSize={10}
              tickMargin={6}
              minTickGap={32}
            />
            <YAxis tickLine={false} axisLine={false} fontSize={10} width={44} allowDecimals={false} />
            <RechartsTooltip
              cursor={{ strokeDasharray: "3 3", stroke: "var(--border)" }}
              content={({ payload, label }) => {
                if (!payload?.length) return null
                const p = payload[0]?.payload as { pages: number; items: number }
                return (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 font-mono text-xs shadow-md">
                    <p className="text-muted-foreground">{String(label)}</p>
                    <p style={{ color: "var(--chart-1)" }}>{p.pages} pages</p>
                    <p style={{ color: "var(--chart-2)" }}>{p.items} items</p>
                  </div>
                )
              }}
            />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 10 }} />
            <Line
              type="monotone"
              dataKey="pages"
              stroke="var(--chart-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="items"
              stroke="var(--chart-2)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}

export function StatsPanel({
  stats: s,
  logparserValid,
  urlSource,
  footer,
}: {
  stats: NonNullable<LogStatsResponse["stats"]>
  logparserValid: boolean
  urlSource?: string
  footer?: React.ReactNode
}) {
  const categories = Object.entries(s.log_categories ?? {})

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCell label="Pages" value={fmt(s.pages)} />
        <KpiCell label="Items" value={fmt(s.items)} />
        <KpiCell label="Runtime" value={s.runtime ?? "N/A"} />
        <KpiCell
          label="Finish reason"
          value={s.finish_reason ?? "N/A"}
          tone={s.finish_reason === "finished" ? "ok" : s.finish_reason === "N/A" ? "muted" : "warn"}
        />
      </div>

      <ProgressChart datas={s.datas} />

      <div className="grid gap-4 *:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Log categories</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {categories.length === 0 && (
              <p className="text-sm text-muted-foreground">No categorised entries.</p>
            )}
            {categories.map(([name, cat]) => (
              <div
                key={name}
                className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 px-3 py-2"
              >
                <span className="font-mono text-xs uppercase tracking-wide">
                  {name.replace(/_logs?$/, "")}
                </span>
                <Badge
                  variant={
                    cat.count > 0 && /critical|error/.test(name)
                      ? "destructive"
                      : cat.count > 0 && /warning|retry|redirect|ignore/.test(name)
                        ? "secondary"
                        : "outline"
                  }
                  className="ml-auto font-mono text-[11px]"
                >
                  {cat.count}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 font-mono text-xs">
              <Row k="first log" v={fmtDateTime(s.first_log_time, "N/A")} />
              <Row k="latest log" v={fmtDateTime(s.latest_log_time, "N/A")} />
              <Row k="updated" v={fmtDateTime(s.last_update_time, "N/A")} />
              <Row k="shutdown" v={s.shutdown_reason} />
              <Row k="logparser" v={logparserValid ? "yes" : "fallback parse"} />
            </dl>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-2">
        {footer}
        {urlSource && (
          <Button variant="outline" size="sm" asChild>
            <a href={urlSource} target="_blank" rel="noreferrer">
              <ExternalLink className="size-3" /> Source
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}

function fmt(v: number | string | null | undefined) {
  if (v == null || v === "N/A") return "N/A"
  return typeof v === "number" ? v.toLocaleString() : String(v)
}

function KpiCell({ label, value, tone }: { label: string; value: string; tone?: "ok" | "warn" | "muted" }) {
  return (
    <Card className="gap-1 py-4">
      <CardContent className="px-4">
        <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p
          className={
            tone === "ok"
              ? "truncate font-mono text-lg font-semibold text-primary"
              : tone === "warn"
                ? "truncate font-mono text-lg font-semibold text-chart-3"
                : "truncate font-mono text-lg font-semibold"
          }
        >
          {value}
        </p>
      </CardContent>
    </Card>
  )
}

function Row({ k, v }: { k: string; v: string | null | undefined }) {
  return (
    <>
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="truncate">{v ?? "N/A"}</dd>
    </>
  )
}
