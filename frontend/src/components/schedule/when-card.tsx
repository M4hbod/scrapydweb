import { useFormContext } from "react-hook-form"
import { ChevronDown, Clock, Play, Timer } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { FormControl, FormField, FormItem, FormLabel } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CronPreview } from "./cron-preview"
import type { ScheduleFormValues } from "@/lib/schedule-payload"

export function WhenCard() {
  const form = useFormContext<ScheduleFormValues>()
  const mode = form.watch("mode")

  return (
    <Card className="gap-3">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Clock className="size-4" /> When
          </CardTitle>
          <FormField
            control={form.control}
            name="mode"
            render={({ field }) => (
              <Tabs
                value={field.value}
                onValueChange={field.onChange}
                className="ml-auto"
              >
                <TabsList className="h-8">
                  <TabsTrigger value="now" className="gap-1.5 px-3 text-xs">
                    <Play className="size-3.5" /> Run now
                  </TabsTrigger>
                  <TabsTrigger value="cron" className="gap-1.5 px-3 text-xs">
                    <Timer className="size-3.5" /> Schedule (cron)
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            )}
          />
        </div>
      </CardHeader>
      {mode === "cron" && (
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Task name</FormLabel>
                  <FormControl>
                    <Input placeholder="auto: task_<id>" {...field} />
                  </FormControl>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="action"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>On save</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="add_fire">Add & fire now</SelectItem>
                      <SelectItem value="add">Add (scheduled)</SelectItem>
                      <SelectItem value="add_pause">Add paused</SelectItem>
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Cron fields (crontab order)
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {(
                [
                  ["minute", "Minute", "0"],
                  ["hour", "Hour", "*/6"],
                  ["day", "Day", "*"],
                  ["month", "Month", "*"],
                  ["day_of_week", "Day of week", "mon-fri"],
                ] as const
              ).map(([key, label, example]) => (
                <FormField
                  key={key}
                  control={form.control}
                  name={key}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{label}</FormLabel>
                      <FormControl>
                        <Input className="font-mono" placeholder={example} {...field} />
                      </FormControl>
                    </FormItem>
                  )}
                />
              ))}
            </div>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              * every · */10 every 10th · 8-22 range · 1,3,5 list · mon-fri names
            </p>
          </div>

          <CronPreview
            spec={{
              minute: form.watch("minute"),
              hour: form.watch("hour"),
              day: form.watch("day"),
              month: form.watch("month"),
              day_of_week: form.watch("day_of_week"),
              second: form.watch("second"),
              week: form.watch("week"),
              year: form.watch("year"),
            }}
          />

          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <ChevronDown className="size-3.5" /> Advanced (second / week / year — usually leave as is)
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3">
              <div className="grid grid-cols-3 gap-3 sm:max-w-md">
                {(
                  [
                    ["second", "Second"],
                    ["week", "Week of year"],
                    ["year", "Year"],
                  ] as const
                ).map(([key, label]) => (
                  <FormField
                    key={key}
                    control={form.control}
                    name={key}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-muted-foreground">{label}</FormLabel>
                        <FormControl>
                          <Input className="font-mono" {...field} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        </CardContent>
      )}
    </Card>
  )
}
