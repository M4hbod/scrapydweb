import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Button } from "@/components/ui/button"
import { StatusPill } from "@/components/status-pill"
import { api } from "@/lib/api"
import { useNode } from "@/lib/node-context"

export function SearchCommand() {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const { node } = useNode()
  const navigate = useNavigate()

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !isTyping(e))) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [])

  const { data, isFetching } = useQuery({
    queryKey: ["search", node, query],
    queryFn: () => api.search(node, query),
    enabled: open && query.trim().length > 0,
    staleTime: 10_000,
  })
  const results = data?.results ?? []

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        className="size-9 justify-center bg-secondary/60 px-0 font-normal text-muted-foreground sm:w-56 sm:justify-start sm:px-3 lg:w-72"
        aria-label="Search"
      >
        <Search className="size-4" />
        <span className="hidden flex-1 text-left text-sm sm:block">Search jobs, spiders…</span>
        <kbd className="pointer-events-none hidden rounded border border-border bg-muted px-1.5 font-mono text-[10px] sm:block">
          ⌘K
        </kbd>
      </Button>
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        commandProps={{ shouldFilter: false }}
        title="Search"
      >
        <CommandInput
          placeholder="Search projects, spiders, job ids…"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>
            {query.trim()
              ? isFetching
                ? "Searching…"
                : "No results."
              : "Type to search jobs across this node."}
          </CommandEmpty>
          {results.length > 0 && (
            <CommandGroup heading={`Jobs on node ${node}`}>
              {results.map((r, i) => (
                <CommandItem
                  key={`${r.project}/${r.spider}/${r.job}/${i}`}
                  value={`${r.project}/${r.spider}/${r.job}/${i}`}
                  onSelect={() => {
                    setOpen(false)
                    navigate("/jobs")
                  }}
                  className="gap-3"
                >
                  <span className="font-mono text-xs text-muted-foreground">{r.project}</span>
                  <span className="font-medium">{r.spider}</span>
                  <span className="truncate font-mono text-xs text-muted-foreground">{r.job}</span>
                  <StatusPill className="ml-auto" status={r.status_class} label={r.status_label} />
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
    </>
  )
}

function isTyping(e: KeyboardEvent) {
  const el = e.target as HTMLElement | null
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)
}
