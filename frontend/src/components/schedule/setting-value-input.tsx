import { Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SETTINGS_BY_KEY } from "@/lib/scrapy-settings"

export function SettingValueInput({
  settingKey,
  value,
  onChange,
}: {
  settingKey: string
  value: string
  onChange: (value: string) => void
}) {
  const def = SETTINGS_BY_KEY.get(settingKey)

  if (def?.type === "bool")
    return (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full font-mono text-xs">
          <SelectValue placeholder={`default: ${def.default}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="True" className="font-mono text-xs">True</SelectItem>
          <SelectItem value="False" className="font-mono text-xs">False</SelectItem>
        </SelectContent>
      </Select>
    )

  if (def?.type === "enum")
    return (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full font-mono text-xs">
          <SelectValue placeholder={`default: ${def.default}`} />
        </SelectTrigger>
        <SelectContent>
          {(def.options ?? []).map((o) => (
            <SelectItem key={o} value={o} className="font-mono text-xs">
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )

  const input = (
    <Input
      type={def?.type === "int" || def?.type === "float" ? "number" : "text"}
      step={def?.type === "float" ? "any" : undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={def ? `default: ${def.default}` : "value"}
      className="font-mono text-xs"
    />
  )

  if (!def?.presets?.length) return input
  return (
    <div className="flex gap-1.5">
      {input}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="outline" size="icon" title="fill from preset">
            <Wand2 className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {def.presets.map((p) => (
            <DropdownMenuItem key={p.label} onSelect={() => onChange(p.value)}>
              {p.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
