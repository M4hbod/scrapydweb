import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Activity, CheckCircle2, Clock, Database, FileText, Server } from "lucide-react"
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { StatusPill } from "@/components/status-pill"
import { api } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { cn } from "@/lib/utils"

const chartConfig = {
  count: { label: "Finished jobs", color: "var(--chart-1)" },
} satisfies ChartConfig

export default function DashboardPage() {
  const { setNode } = useNode()
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    refetchInterval: 15_000,
  })
  const d = data?.dashboard

  if (isLoading) return <DashboardSkeleton />
  if (data && (data.nodes ?? []).length === 0)
    return (
      <Card className="mx-auto max-w-2xl">
        <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
          <Server className="size-8 text-muted-foreground" />
          <h3 className="text-base font-semibold">No scrapyd servers configured</h3>
          <p className="max-w-md text-sm text-muted-foreground">
            Add the address of your scrapyd server (e.g.{" "}
            <span className="font-mono text-xs">127.0.0.1:6800</span>, with optional basic-auth
            credentials) to start managing spiders.
          </p>
          <Link
            to="/settings"
            className="mt-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Configure servers
          </Link>
        </CardContent>
      </Card>
    )
  if (!d)
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Dashboard unavailable — no data from the cluster yet.
        </CardContent>
      </Card>
    )

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi icon={Activity} label="Running" value={d.kpi.running} accent />
        <Kpi icon={Clock} label="Pending" value={d.kpi.pending} />
        <Kpi icon={CheckCircle2} label="Finished" value={d.kpi.finished} />
        <Kpi icon={FileText} label="Pages" value={d.kpi.pages} />
        <Kpi icon={Database} label="Items" value={d.kpi.items} />
      </div>

      <div className="grid gap-4 *:min-w-0 lg:grid-cols-3">
        {/* node grid */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold">Scrapyd Nodes</CardTitle>
            <Badge variant="outline" className="font-mono text-[11px]">
              {d.nodes_online}/{d.nodes_total} online
            </Badge>
          </CardHeader>
          <CardContent className="grid gap-3 *:min-w-0 sm:grid-cols-2">
            {d.nodes.map((n) => (
              <Link
                key={n.index}
                to="/jobs"
                onClick={() => setNode(n.index)}
                className="group rounded-lg border border-border bg-secondary/40 p-3 transition-colors hover:border-primary/40"
              >
                <div className="flex items-center gap-2">
                  <Server className="size-4 text-muted-foreground" />
                  <span className="truncate font-mono text-xs font-medium">
                    {n.index}. {n.server}
                  </span>
                  {n.group && (
                    <Badge variant="secondary" className="ml-auto text-[10px]">
                      {n.group}
                    </Badge>
                  )}
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-xs">
                  <Stat label="run" value={n.running} className="text-primary" />
                  <Stat label="pend" value={n.pending} className="text-chart-3" />
                  <Stat label="fin" value={n.finished} className="text-muted-foreground" />
                </div>
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${n.load_pct}%` }}
                  />
                </div>
                <div className="mt-1.5 flex justify-between text-[11px] text-muted-foreground">
                  <span>
                    {n.pages.toLocaleString()} pages · {n.items.toLocaleString()} items
                  </span>
                  <span>{n.last || "no activity"}</span>
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>

        {/* throughput */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold">Throughput</CardTitle>
            <span className="font-mono text-[11px] text-muted-foreground">
              {d.throughput_total} finished / 14d
            </span>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="h-48 w-full">
              <BarChart data={d.throughput} margin={{ left: 0, right: 0 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={6}
                  fontSize={10}
                  interval="preserveStartEnd"
                />
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      {/* activity feed */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Recent Activity</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          {d.activity.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">No recent jobs.</p>
          )}
          {[...d.activity].reverse().map((e, i) => (
            <Link
              key={i}
              to={`/log/${e.node}/stats/${encodeURIComponent(e.project)}/${encodeURIComponent(e.spider)}/${encodeURIComponent(e.job)}${e.status_class === "fin" ? "?finished=1" : ""}`}
              onClick={() => setNode(e.node)}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-sm transition-colors hover:bg-secondary/30"
            >
              <StatusPill status={e.status_class} label={e.status_label} />
              <span className="font-medium">{e.spider}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {e.project} · {e.job}
              </span>
              <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-muted-foreground">
                {e.pages != null && <span>{e.pages.toLocaleString()} pages</span>}
                {e.items != null && <span>{e.items.toLocaleString()} items</span>}
                {e.runtime && <span>{e.runtime}</span>}
                <span>{e.when}</span>
              </span>
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function Kpi({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ElementType
  label: string
  value: number
  accent?: boolean
}) {
  return (
    <Card className="gap-2 py-4">
      <CardContent className="flex items-center gap-3 px-4">
        <div
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-lg",
            accent ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground",
          )}
        >
          <Icon className="size-4.5" />
        </div>
        <div className="min-w-0">
          <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <p className={cn("truncate font-mono text-xl font-semibold", accent && "text-primary")}>
            {value.toLocaleString()}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

function Stat({ label, value, className }: { label: string; value: number; className?: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className={cn("font-semibold", className)}>{value}</span>
      <span className="text-[10px] uppercase text-muted-foreground">{label}</span>
    </span>
  )
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-[76px] rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 *:min-w-0 lg:grid-cols-3">
        <Skeleton className="h-64 rounded-xl lg:col-span-2" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
      <Skeleton className="h-48 rounded-xl" />
    </div>
  )
}
