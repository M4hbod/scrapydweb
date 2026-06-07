import { useFormContext } from "react-hook-form"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Crosshair } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { NodeMultiSelect } from "@/components/node-multi-select"
import { getJSON } from "@/lib/api"
import { LATEST, type ScheduleFormValues } from "@/lib/schedule-payload"

export function TargetCard({ node }: { node: number }) {
  const form = useFormContext<ScheduleFormValues>()
  const project = form.watch("project")
  const version = form.watch("_version")

  const { data: projects } = useQuery({
    queryKey: ["listprojects", node],
    queryFn: () => getJSON<{ projects?: string[] }>(`/${node}/api/listprojects/`),
  })
  const { data: versions } = useQuery({
    queryKey: ["listversions", node, project],
    queryFn: () =>
      getJSON<{ versions?: string[] }>(`/${node}/api/listversions/${encodeURIComponent(project)}/`),
    enabled: !!project,
  })
  const { data: spiders } = useQuery({
    queryKey: ["listspiders", node, project, version],
    queryFn: () =>
      getJSON<{ spiders?: string[] }>(
        // legacy proxy treats the literal DEFAULT_LATEST_VERSION segment as "omit _version"
        `/${node}/api/listspiders/${encodeURIComponent(project)}/${encodeURIComponent(version)}/`,
      ),
    enabled: !!project,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Crosshair className="size-4" /> Target
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField
            control={form.control}
            name="project"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Project</FormLabel>
                <Select
                  value={field.value}
                  onValueChange={(v) => {
                    field.onChange(v)
                    form.setValue("_version", LATEST)
                    form.setValue("spider", "")
                  }}
                >
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="project" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {(projects?.projects ?? []).map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="_version"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Version</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value={LATEST}>{LATEST}</SelectItem>
                    {(versions?.versions ?? []).map((v) => (
                      <SelectItem key={v} value={v}>
                        {v}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="spider"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Spider</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="spider" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {(spiders?.spiders ?? []).map((sp) => (
                      <SelectItem key={sp} value={sp}>
                        {sp}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="nodes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Run on nodes</FormLabel>
              <FormControl>
                <NodeMultiSelect value={field.value} onChange={field.onChange} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Collapsible>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ChevronDown className="size-3.5" /> Advanced
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-3">
            <FormField
              control={form.control}
              name="jobid"
              render={({ field }) => (
                <FormItem className="sm:max-w-sm">
                  <FormLabel>Job ID (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="auto: current timestamp" className="font-mono" {...field} />
                  </FormControl>
                </FormItem>
              )}
            />
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}
