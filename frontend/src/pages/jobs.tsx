import * as React from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table"
import {
  BarChart3,
  CircleCheck,
  CircleEllipsis,
  CircleX,
  CirclePlay,
  Code2,
  Download,
  FileText,
  Play,
  Search,
  Square,
} from "lucide-react"
import {
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { StatusPill } from "@/components/status-pill"
import { api, postJSON, type JobRow } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { cn } from "@/lib/utils"

const STATUS: Record<string, { label: string; cls: string }> = {
  "0": { label: "PENDING", cls: "pend" },
  "1": { label: "RUNNING", cls: "run" },
  "2": { label: "FINISHED", cls: "fin" },
}

export default function JobsPage() {
  const { node } = useNode()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const status = params.get("status") ?? "all"
  const page = Math.max(1, Number(params.get("page")) || 1)
  const perPage = Number(params.get("per_page")) || 100

  const setFilter = (key: "q" | "status" | "page" | "per_page", value: string) => {
    const next = new URLSearchParams(params)
    if (!value || value === "all" || (key === "page" && value === "1") ||
        (key === "per_page" && value === "100")) next.delete(key)
    else next.set(key, value)
    if (key !== "page") next.delete("page") // filters/per-page reset to page 1
    setParams(next, { replace: true })
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["jobs", node, page, perPage],
    queryFn: () => api.jobs(node, page, perPage),
    refetchInterval: 10_000,
    staleTime: 5_000, // route remounts reuse the cache instead of blocking on a refetch
    placeholderData: (prev) => prev,
  })

  const action = useMutation({
    mutationFn: ({ url }: { url: string; verb: string }) => postJSON<Record<string, unknown>>(url),
    onSuccess: (res, { verb }) => {
      const status = (res as { status?: string }).status
      if (status === "ok") toast.success(`${verb} sent`)
      else toast.error(`${verb} failed: ${JSON.stringify(res).slice(0, 200)}`)
      qc.invalidateQueries({ queryKey: ["jobs", node] })
    },
    onError: (err, { verb }) => toast.error(`${verb} failed: ${err.message}`),
  })

  const columns = React.useMemo<ColumnDef<JobRow>[]>(
    () => [
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => {
          const j = row.original
          if (j.status === "2" && j.finish_reason && j.finish_reason !== "finished")
            return <StatusPill status="err" label="FAILED" />
          const s = STATUS[j.status] ?? STATUS["2"]
          return <StatusPill status={s.cls} label={s.label} />
        },
      },
      {
        accessorKey: "spider",
        header: "Spider",
        cell: ({ row }) => (
          <span className="font-mono text-xs">
            <span className="text-muted-foreground">{row.original.project}/</span>
            <span className="font-medium text-foreground">{row.original.spider}</span>
          </span>
        ),
      },
      {
        accessorKey: "job",
        header: "Job ID",
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-muted-foreground">{getValue<string>()}</span>
        ),
      },
      {
        accessorKey: "version",
        header: "Version",
        cell: ({ getValue }) => {
          const v = getValue<string | null>()
          return v ? (
            <span className="font-mono text-[11px] text-muted-foreground" title={v}>
              {v.length > 16 ? `${v.slice(0, 16)}…` : v}
            </span>
          ) : (
            <span className="font-mono text-xs text-muted-foreground/50">–</span>
          )
        },
      },
      {
        accessorKey: "pages",
        header: () => <span className="block text-right">Pages</span>,
        cell: ({ getValue }) => <Num v={getValue<number | null>()} />,
      },
      {
        accessorKey: "items",
        header: () => <span className="block text-right">Items</span>,
        cell: ({ getValue }) => <Num v={getValue<number | null>()} />,
      },
      {
        accessorKey: "runtime",
        header: "Duration",
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{getValue<string | null>() ?? "–"}</span>
        ),
      },
      {
        accessorKey: "start",
        header: "Start",
        cell: ({ getValue }) => <Time v={getValue<string | null>()} />,
      },
      {
        accessorKey: "finish",
        header: "Finish",
        cell: ({ getValue }) => <Time v={getValue<string | null>()} />,
      },
      {
        id: "actions",
        header: () => <span className="block text-right">Actions</span>,
        cell: ({ row }) => {
          const j = row.original
          return (
            <div className="flex justify-end gap-1">
              <IconAction
                label="Stats"
                icon={BarChart3}
                onClick={() =>
                  navigate(
                    `/log/${node}/stats/${j.project}/${j.spider}/${j.job}${j.status === "2" ? "?finished=1" : ""}`,
                  )
                }
              />
              <IconAction
                label="Log"
                icon={FileText}
                onClick={() =>
                  navigate(
                    `/log/${node}/utf8/${j.project}/${j.spider}/${j.job}${j.status === "2" ? "?finished=1" : ""}`,
                  )
                }
              />
              {j.version && (
                <IconAction
                  label={`View code (${j.version})`}
                  icon={Code2}
                  onClick={() =>
                    navigate(
                      `/code/${encodeURIComponent(j.project)}/${encodeURIComponent(j.version!)}`,
                    )
                  }
                />
              )}
              {j.href_items && (
                <IconAction
                  label="Download items (.jl)"
                  icon={Download}
                  onClick={() => {
                    const file = j.href_items!.split("/").pop()!
                    window.location.href = `/api/${node}/download/items/${encodeURIComponent(j.project)}/${encodeURIComponent(j.spider)}/${encodeURIComponent(file)}`
                  }}
                />
              )}
              {j.status === "1" ? (
                <IconAction
                  label="Stop"
                  icon={Square}
                  destructive
                  onClick={() => action.mutate({ url: j.url_stop, verb: "Stop" })}
                />
              ) : (
                <IconAction
                  label="Run again"
                  icon={Play}
                  onClick={() => action.mutate({ url: j.url_start, verb: "Start" })}
                />
              )}
            </div>
          )
        },
      },
    ],
    [action, node, navigate],
  )

  const all = React.useMemo(() => data?.jobs ?? [], [data])
  const jobs = React.useMemo(() => {
    const needle = q.trim().toLowerCase()
    const failed = (j: JobRow) =>
      j.status === "2" && !!j.finish_reason && j.finish_reason !== "finished"
    return all.filter((j) => {
      if (status === "failed") {
        if (!failed(j)) return false
      } else if (status !== "all" && j.status !== status) return false
      if (!needle) return true
      return (
        j.project.toLowerCase().includes(needle) ||
        j.spider.toLowerCase().includes(needle) ||
        j.job.toLowerCase().includes(needle)
      )
    })
  }, [all, q, status])
  // defer the heavy table/chart re-render so the clicked control updates instantly
  const deferredJobs = React.useDeferredValue(jobs)
  const isStale = deferredJobs !== jobs
  const table = useReactTable({ data: deferredJobs, columns, getCoreRowModel: getCoreRowModel() })

  if (isLoading)
    return (
      <div className="mx-auto max-w-7xl">
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )

  if (error || data?.status === "error")
    return (
      <Card className="mx-auto max-w-7xl">
        <CardContent className="py-10 text-center text-sm text-destructive">
          {data?.message ?? (error as Error | null)?.message ?? "Failed to load jobs."}
        </CardContent>
      </Card>
    )

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Jobs</h2>
        <span className="font-mono text-xs text-muted-foreground">
          {jobs.length}/{data?.total ?? 0} jobs · node {node}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setFilter("q", e.target.value)}
              placeholder="Filter project / spider / job id"
              className="h-8 w-64 pl-8 text-xs"
            />
          </div>
          <div className="inline-flex h-8 items-center gap-0.5 rounded-lg border border-border bg-secondary/60 p-0.5">
            {(
              [
                ["all", "All", null],
                ["1", "Running", CirclePlay],
                ["2", "Finished", CircleCheck],
                ["failed", "Failed", CircleX],
                ["0", "Pending", CircleEllipsis],
              ] as const
            ).map(([value, label, Icon]) => (
              <Tooltip key={value}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label={label}
                    onClick={() => setFilter("status", value)}
                    className={cn(
                      "flex h-7 items-center justify-center rounded-md px-2.5 text-xs transition-colors",
                      status === value
                        ? "bg-muted text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {Icon ? <Icon className="size-4" /> : "All"}
                  </button>
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            ))}
          </div>
        </div>
      </div>
      <DurationChart jobs={deferredJobs} />
      <Card className={cn("py-0 transition-opacity", isStale && "opacity-60")}>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id} className="hover:bg-transparent">
                  {hg.headers.map((h) => (
                    <TableHead
                      key={h.id}
                      className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground"
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={columns.length} className="py-10 text-center text-muted-foreground">
                    {q || status !== "all"
                      ? "No jobs match the current filter."
                      : "No jobs on this node yet."}
                  </TableCell>
                </TableRow>
              )}
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} className="hover:bg-secondary/30">
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="py-2.5">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={String(perPage)} onValueChange={(v) => setFilter("per_page", v)}>
          <SelectTrigger size="sm" className="w-32 font-mono text-xs">
            <SelectValue placeholder={`${perPage} / page`} />
          </SelectTrigger>
          <SelectContent>
            {[25, 50, 100, 200, 500, 1000].map((n) => (
              <SelectItem key={n} value={String(n)} className="font-mono text-xs">
                {n} / page
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(data?.pages ?? 1) > 1 && (
          <div className="ml-auto flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">
              page {data?.page ?? page} / {data?.pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={page <= 1}
              onClick={() => setFilter("page", String(page - 1))}
            >
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={page >= (data?.pages ?? 1)}
              onClick={() => setFilter("page", String(page + 1))}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function parseRuntime(rt: string | null): number | null {
  // "H:MM:SS" or "D days, H:MM:SS" -> seconds
  if (!rt) return null
  let days = 0
  let rest = rt
  const dm = /^(\d+) days?, (.*)$/.exec(rt)
  if (dm) {
    days = Number(dm[1])
    rest = dm[2]
  }
  const parts = rest.split(":").map(Number)
  if (parts.some(Number.isNaN) || parts.length !== 3) return null
  return days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]
}

function fmtDuration(s: number) {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

const RUN_COLORS = {
  ok: "#22c55e",
  bad: "#ef4444",
  running: "#38bdf8",
  unknown: "#64748b",
}

function runColor(j: JobRow) {
  if (j.status === "1") return RUN_COLORS.running
  if (j.finish_reason === "finished") return RUN_COLORS.ok
  if (j.finish_reason) return RUN_COLORS.bad // shutdown / closespider_* / cancelled...
  return RUN_COLORS.unknown
}

function DurationChart({ jobs }: { jobs: JobRow[] }) {
  const points = React.useMemo(
    () =>
      jobs
        .filter((j) => j.start)
        .map((j) => {
          const secs = parseRuntime(j.runtime)
          return {
            x: new Date(j.start!.replace(" ", "T")).getTime(),
            y: Math.max(1, secs ?? 1),
            fill: runColor(j),
            job: j,
          }
        }),
    [jobs],
  )
  if (points.length < 2) return null

  return (
    <Card className="gap-2 py-4">
      <CardContent className="px-2">
        <ResponsiveContainer width="100%" height={180}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t) =>
                new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
              }
              tickLine={false}
              axisLine={false}
              fontSize={10}
              tickMargin={6}
            />
            <YAxis
              dataKey="y"
              type="number"
              scale="log"
              domain={["auto", "auto"]}
              tickFormatter={(v) => fmtDuration(Number(v))}
              tickLine={false}
              axisLine={false}
              fontSize={10}
              width={56}
              label={{
                value: "duration",
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: "var(--muted-foreground)" },
              }}
            />
            <RechartsTooltip
              cursor={{ strokeDasharray: "3 3", stroke: "var(--border)" }}
              content={({ payload }) => {
                const p = payload?.[0]?.payload as { job: JobRow; y: number } | undefined
                if (!p) return null
                return (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 font-mono text-xs shadow-md">
                    <p className="font-medium">{p.job.spider}</p>
                    <p className="text-muted-foreground">{p.job.job}</p>
                    <p>
                      {fmtDuration(p.y)} · {p.job.pages ?? "–"} pages · {p.job.items ?? "–"} items
                    </p>
                    <p className="text-muted-foreground">{p.job.start}</p>
                    {p.job.finish_reason && (
                      <p style={{ color: runColor(p.job) }}>{p.job.finish_reason}</p>
                    )}
                  </div>
                )
              }}
            />
            <Scatter data={points} isAnimationActive={false}>
              {points.map((pt, i) => (
                <Cell key={i} fill={pt.fill} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
        <div className="flex justify-end gap-4 px-3 font-mono text-[10px] text-muted-foreground">
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: RUN_COLORS.ok }} />finished</span>
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: RUN_COLORS.bad }} />aborted</span>
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: RUN_COLORS.running }} />running</span>
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: RUN_COLORS.unknown }} />no stats</span>
        </div>
      </CardContent>
    </Card>
  )
}

function Num({ v }: { v: number | null }) {
  return (
    <span className="block text-right font-mono text-xs">
      {v != null ? v.toLocaleString() : "–"}
    </span>
  )
}

function Time({ v }: { v: string | null }) {
  return <span className="font-mono text-xs text-muted-foreground">{v ?? "–"}</span>
}

function IconAction({
  label,
  icon: Icon,
  onClick,
  destructive,
}: {
  label: string
  icon: React.ElementType
  onClick: () => void
  destructive?: boolean
}) {
  // native title instead of a Radix tooltip: with 100 rows x 3 actions the
  // portal-based tooltips dominate render time and make filter toggles laggy
  return (
    <Button
      variant="ghost"
      size="icon"
      className={destructive ? "size-7 text-destructive hover:text-destructive" : "size-7"}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      <Icon className="size-3.5" />
    </Button>
  )
}
