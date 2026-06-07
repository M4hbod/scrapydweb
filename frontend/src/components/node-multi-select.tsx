import { useQuery } from "@tanstack/react-query"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type NodeInfo } from "@/lib/api"
import { cn } from "@/lib/utils"

export function NodeMultiSelect({
  value,
  onChange,
}: {
  value: number[]
  onChange: (nodes: number[]) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["nodes"],
    queryFn: api.nodes,
    staleTime: 60_000,
  })
  if (isLoading) return <Skeleton className="h-8 w-64 rounded-lg" />
  const all: NodeInfo[] = data?.nodes ?? []
  const toggle = (n: number) =>
    onChange(value.includes(n) ? value.filter((x) => x !== n) : [...value, n].sort((a, b) => a - b))
  return (
    <div className="flex flex-wrap gap-1.5">
      {all.map((n) => {
        const active = value.includes(n.node)
        return (
          <button
            key={n.node}
            type="button"
            onClick={() => toggle(n.node)}
            className={cn(
              "rounded-full border px-3 py-1 font-mono text-xs transition-colors",
              active
                ? "border-primary/60 bg-primary/15 text-primary"
                : "border-border bg-secondary/40 text-muted-foreground hover:border-primary/30",
            )}
          >
            {n.node} · {n.server}
          </button>
        )
      })}
      {value.length === 0 && (
        <span className="self-center text-xs text-destructive">select at least one node</span>
      )}
    </div>
  )
}
