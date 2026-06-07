import { useFieldArray, useFormContext } from "react-hook-form"
import { Braces, Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FormControl, FormField, FormItem, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import type { ScheduleFormValues } from "@/lib/schedule-payload"

export function ArgsCard() {
  const form = useFormContext<ScheduleFormValues>()
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "args" })

  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Braces className="size-4" /> Spider arguments
          <span className="font-mono text-xs font-normal text-muted-foreground">
            passed to the spider's __init__ (-a key=value)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {fields.length === 0 && (
          <p className="text-xs text-muted-foreground">No arguments.</p>
        )}
        {fields.map((f, i) => (
          <div key={f.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] items-start gap-2">
            <FormField
              control={form.control}
              name={`args.${i}.key`}
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input placeholder="name" className="font-mono text-xs" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name={`args.${i}.value`}
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input placeholder="value" className="font-mono text-xs" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="button" variant="ghost" size="icon" onClick={() => remove(i)} title="remove">
              <X className="size-4" />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="self-start text-muted-foreground"
          onClick={() => append({ key: "", value: "" })}
        >
          <Plus className="size-3.5" /> Add argument
        </Button>
      </CardContent>
    </Card>
  )
}
