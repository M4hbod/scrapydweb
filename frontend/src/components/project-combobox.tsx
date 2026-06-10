import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Check, ChevronsUpDown, Plus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ProjectDialog } from "@/components/project-dialog"
import { api, getJSON } from "@/lib/api"
import { cn } from "@/lib/utils"

// Pick a project: union of registered projects + projects already on the
// node's scrapyd, with a "Create a project" escape hatch as the last option.
export function ProjectComboBox({
  node,
  value,
  onChange,
}: {
  node: number
  value: string
  onChange: (name: string) => void
}) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")
  const [creating, setCreating] = React.useState(false)

  const { data: registered, refetch } = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects,
    staleTime: 30_000,
  })
  const { data: scrapyd } = useQuery({
    queryKey: ["listprojects", node],
    queryFn: () => getJSON<{ projects?: string[] }>(`/${node}/api/listprojects/`),
  })

  const registeredNames = new Set((registered?.projects ?? []).map((p) => p.name))
  const names = Array.from(
    new Set([...(registered?.projects ?? []).map((p) => p.name), ...(scrapyd?.projects ?? [])]),
  ).sort((a, b) => a.localeCompare(b))

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className={cn("w-full justify-between font-mono text-sm font-normal",
              !value && "text-muted-foreground")}
          >
            <span className="truncate">{value || "pick a project…"}</span>
            <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[320px] p-0" align="start">
          <Command>
            <CommandInput placeholder="search projects…" value={search} onValueChange={setSearch} />
            <CommandList className="max-h-72">
              <CommandEmpty>no matching project</CommandEmpty>
              <CommandGroup>
                {names.map((name) => (
                  <CommandItem
                    key={name}
                    value={name}
                    onSelect={() => {
                      onChange(name)
                      setOpen(false)
                    }}
                  >
                    <Check className={cn("size-3.5", value === name ? "opacity-100" : "opacity-0")} />
                    <span className="flex-1 truncate font-mono text-xs">{name}</span>
                    {registeredNames.has(name) && (
                      <Badge variant="secondary" className="text-[10px]">registered</Badge>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
              <CommandGroup>
                <CommandItem
                  value="__create__"
                  onSelect={() => {
                    setOpen(false)
                    setCreating(true)
                  }}
                >
                  <Plus className="size-3.5" />
                  <span className="text-xs">Create a project{search ? ` "${search}"` : ""}</span>
                </CommandItem>
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {creating && (
        <ProjectDialog
          project={null}
          defaultName={search}
          onClose={() => setCreating(false)}
          onSaved={(p) => {
            refetch()
            onChange(p.name)
          }}
        />
      )}
    </>
  )
}
