import { Link, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Server, TriangleAlert } from "lucide-react"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SearchCommand } from "@/components/search-command"
import { api } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { cn } from "@/lib/utils"

const TITLES: [string, string][] = [
  ["/jobs", "Jobs"],
  ["/tasks", "Timer Tasks"],
  ["/schedule", "Run Spider"],
  ["/deploy", "Deploy Project"],
  ["/projects", "Projects"],
  ["/settings", "Settings"],
  ["/code/", "Code"],
  ["/log/", "Log Viewer"],
]

function pageTitle(pathname: string) {
  for (const [prefix, title] of TITLES) if (pathname.startsWith(prefix)) return title
  return "Dashboard"
}

export function Topbar() {
  const location = useLocation()
  const { node, setNode, nodes } = useNode()

  const { data: status } = useQuery({
    queryKey: ["daemonstatus", node],
    queryFn: () => api.daemonstatus(node),
    refetchInterval: 10_000,
    retry: false,
    enabled: nodes.length > 0,
  })
  const online = status?.status === "ok"

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="!h-5" />
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
          scrapydweb /
        </span>
        <h1 className="truncate text-sm font-semibold">{pageTitle(location.pathname)}</h1>
      </div>

      <div className="ml-auto flex min-w-0 items-center gap-3">
        <div className="hidden items-center gap-2 lg:flex">
          <Chip label="running" value={status?.running} tone="run" />
          <Chip label="pending" value={status?.pending} tone="pend" />
          <Chip label="finished" value={status?.finished} tone="fin" />
        </div>
        <Separator orientation="vertical" className="!h-5 hidden lg:block" />
        <SearchCommand />
        {nodes.length === 0 ? (
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 rounded-md border border-chart-3/40 bg-chart-3/10 px-2.5 py-1.5 font-mono text-[11px] text-chart-3 hover:border-chart-3/70"
          >
            <TriangleAlert className="size-3.5" /> no servers — configure
          </Link>
        ) : (
          <Select value={String(node)} onValueChange={(v) => setNode(Number(v))}>
            <SelectTrigger
              size="sm"
              className="w-20 min-w-0 shrink gap-2 overflow-hidden bg-secondary/60 font-mono text-xs *:data-[slot=select-value]:truncate sm:w-48"
            >
              <span
                className={cn(
                  "size-2 shrink-0 rounded-full",
                  online ? "bg-primary" : "bg-destructive",
                )}
              />
              <SelectValue placeholder="node" />
            </SelectTrigger>
            <SelectContent>
              {nodes.map((n) => (
                <SelectItem key={n.node} value={String(n.node)} className="font-mono text-xs">
                  <Server className="size-3.5 text-muted-foreground" />
                  {n.node}. {n.server}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
    </header>
  )
}

function Chip({
  label,
  value,
  tone,
}: {
  label: string
  value: number | undefined
  tone: "run" | "pend" | "fin"
}) {
  const tones = {
    run: "text-primary border-primary/30 bg-accent/60",
    pend: "text-chart-3 border-chart-3/30 bg-chart-3/10",
    fin: "text-muted-foreground border-border bg-muted/40",
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[11px]",
        tones[tone],
      )}
    >
      <span className="uppercase tracking-wide opacity-70">{label}</span>
      <span className="font-semibold">{value ?? "–"}</span>
    </span>
  )
}
