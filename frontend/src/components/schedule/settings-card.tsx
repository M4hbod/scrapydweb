import { useFieldArray, useFormContext } from "react-hook-form"
import { Plus, SlidersHorizontal, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FormField, FormItem, FormMessage } from "@/components/ui/form"
import { SettingKeyCombobox } from "./setting-key-combobox"
import { SettingValueInput } from "./setting-value-input"
import { SETTINGS_BY_KEY } from "@/lib/scrapy-settings"
import type { ScheduleFormValues } from "@/lib/schedule-payload"

export function SettingsCard() {
  const form = useFormContext<ScheduleFormValues>()
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "settings" })
  const rows = form.watch("settings")
  const usedKeys = new Set(rows.map((r) => r.key).filter(Boolean))

  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <SlidersHorizontal className="size-4" /> Scrapy settings
          <span className="font-mono text-xs font-normal text-muted-foreground">
            override per run — anything not listed keeps the project default
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {fields.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No overrides. The spider runs with its project settings.
          </p>
        )}
        {fields.map((f, i) => {
          const def = SETTINGS_BY_KEY.get(rows[i]?.key ?? "")
          return (
            <div key={f.id} className="flex flex-col gap-1">
              <div className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] items-start gap-2">
                <FormField
                  control={form.control}
                  name={`settings.${i}.key`}
                  render={({ field }) => (
                    <FormItem>
                      <SettingKeyCombobox
                        value={field.value}
                        onChange={(k) => {
                          field.onChange(k)
                          form.setValue(`settings.${i}.value`, "")
                        }}
                        usedKeys={usedKeys}
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={`settings.${i}.value`}
                  render={({ field }) => (
                    <FormItem>
                      <SettingValueInput
                        settingKey={rows[i]?.key ?? ""}
                        value={field.value}
                        onChange={field.onChange}
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(i)}
                  title="remove"
                >
                  <X className="size-4" />
                </Button>
              </div>
              {def && (
                <p className="px-1 text-[11px] text-muted-foreground">
                  {def.description} · default: <span className="font-mono">{def.default || "—"}</span>
                </p>
              )}
            </div>
          )
        })}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="self-start text-muted-foreground"
          onClick={() => append({ key: "", value: "" })}
        >
          <Plus className="size-3.5" /> Add setting
        </Button>
      </CardContent>
    </Card>
  )
}
