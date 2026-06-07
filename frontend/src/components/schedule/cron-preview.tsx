import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { CalendarClock } from "lucide-react"
import { postForm } from "@/lib/api"

export interface CronSpec {
  minute: string
  hour: string
  day: string
  month: string
  day_of_week: string
  second: string
  week: string
  year: string
}

interface CronPreviewResponse {
  status: string
  next_runs?: string[]
  message?: string
}

// Debounced /api/cron/preview query. queryKey is the debounced spec, so the
// summary panel and the when-card share one request via the query cache.
export function useCronPreview(spec: CronSpec, enabled = true) {
  const [debounced, setDebounced] = React.useState(spec)
  const key = JSON.stringify(spec)
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(spec), 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return useQuery({
    queryKey: ["cron-preview", JSON.stringify(debounced)],
    queryFn: () =>
      postForm<CronPreviewResponse>("/api/cron/preview", debounced as unknown as Record<string, string>),
    staleTime: 30_000,
    enabled,
  })
}

export function CronPreview({ spec }: { spec: CronSpec }) {
  const { data } = useCronPreview(spec)

  return (
    <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <CalendarClock className="size-3.5" /> Next runs
      </p>
      {data?.status === "ok" &&
        (data.next_runs?.length ? (
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs">
            {data.next_runs.map((t, i) => (
              <span key={t} className={i === 0 ? "text-primary" : "text-foreground/80"}>
                {t}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-1.5 font-mono text-xs text-chart-3">never fires — check the fields</p>
        ))}
      {data?.status === "error" && (
        <p className="mt-1.5 font-mono text-xs text-destructive">{data.message}</p>
      )}
      {!data && <p className="mt-1.5 font-mono text-xs text-muted-foreground">…</p>}
    </div>
  )
}
