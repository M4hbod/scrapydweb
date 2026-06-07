import * as React from "react"
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
import { SCRAPY_SETTINGS, SETTING_KEY_RE } from "@/lib/scrapy-settings"
import { cn } from "@/lib/utils"

export function SettingKeyCombobox({
  value,
  onChange,
  usedKeys,
}: {
  value: string
  onChange: (key: string) => void
  usedKeys: Set<string>
}) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")

  const custom = search.trim().toUpperCase()
  const customValid =
    SETTING_KEY_RE.test(custom) &&
    !SCRAPY_SETTINGS.some((s) => s.key === custom) &&
    !usedKeys.has(custom)

  const pick = (key: string) => {
    onChange(key)
    setOpen(false)
    setSearch("")
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "w-full justify-between font-mono text-xs font-normal",
            !value && "text-muted-foreground",
          )}
        >
          <span className="truncate">{value || "pick a setting…"}</span>
          <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[340px] p-0" align="start">
        <Command>
          <CommandInput
            placeholder="search settings or type a custom key…"
            value={search}
            onValueChange={setSearch}
          />
          <CommandList className="max-h-72">
            <CommandEmpty>
              {customValid ? "" : "no matching setting"}
            </CommandEmpty>
            {customValid && (
              <CommandGroup>
                <CommandItem value={`custom-${custom}`} onSelect={() => pick(custom)}>
                  <Plus className="size-3.5" />
                  <span className="font-mono text-xs">
                    use custom key <b>{custom}</b>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
            <CommandGroup>
              {SCRAPY_SETTINGS.filter((s) => s.key === value || !usedKeys.has(s.key)).map((s) => (
                <CommandItem key={s.key} value={s.key} onSelect={() => pick(s.key)}>
                  <Check className={cn("size-3.5", value === s.key ? "opacity-100" : "opacity-0")} />
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate font-mono text-xs">{s.key}</span>
                    <span className="truncate text-[11px] text-muted-foreground">
                      {s.description}
                    </span>
                  </div>
                  <Badge variant="secondary" className="ml-auto shrink-0 font-mono text-[10px]">
                    {s.type}
                  </Badge>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
