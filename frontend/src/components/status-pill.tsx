import { cn } from "@/lib/utils"

const STYLES: Record<string, string> = {
  run: "bg-accent text-accent-foreground border-primary/30",
  pend: "bg-chart-3/15 text-chart-3 border-chart-3/30",
  fin: "bg-muted text-muted-foreground border-border",
  err: "bg-destructive/15 text-destructive border-destructive/30",
}

export function StatusPill({
  status,
  label,
  className,
}: {
  status: string
  label: string
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide",
        STYLES[status] ?? STYLES.fin,
        className,
      )}
    >
      {status === "run" && <span className="size-1.5 animate-pulse rounded-full bg-primary" />}
      {label}
    </span>
  )
}
