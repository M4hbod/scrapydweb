import * as React from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { ChevronDown, Play, TerminalSquare, Timer } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Form,
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
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { CalendarClock } from "lucide-react"
import { getJSON, postForm } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { cn } from "@/lib/utils"

const LATEST = "default: the latest version"

const schema = z.object({
  project: z.string().min(1, "Pick a project"),
  _version: z.string(),
  spider: z.string().min(1, "Pick a spider"),
  jobid: z.string(),
  USER_AGENT: z.string(),
  ROBOTSTXT_OBEY: z.string(),
  COOKIES_ENABLED: z.string(),
  CONCURRENT_REQUESTS: z.string(),
  DOWNLOAD_DELAY: z.string(),
  additional: z.string(),
  // timer task
  timer: z.boolean(),
  name: z.string(),
  action: z.enum(["add_fire", "add", "add_pause"]),
  year: z.string(),
  month: z.string(),
  day: z.string(),
  week: z.string(),
  day_of_week: z.string(),
  hour: z.string(),
  minute: z.string(),
  second: z.string(),
})

type FormValues = z.infer<typeof schema>

export default function SchedulePage() {
  const { node } = useNode()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [cmd, setCmd] = React.useState("")
  const [filename, setFilename] = React.useState("")

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      project: params.get("project") ?? "",
      _version: params.get("version") ?? LATEST,
      spider: params.get("spider") ?? "",
      jobid: "",
      USER_AGENT: "",
      ROBOTSTXT_OBEY: "",
      COOKIES_ENABLED: "",
      CONCURRENT_REQUESTS: "",
      DOWNLOAD_DELAY: "",
      additional: "",
      timer: params.get("timer") === "1",
      name: "",
      action: "add_fire",
      year: "*",
      month: "*",
      day: "*",
      week: "*",
      day_of_week: "*",
      hour: "*",
      minute: "0",
      second: "0",
    },
  })
  const project = form.watch("project")
  const version = form.watch("_version")
  const timer = form.watch("timer")

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

  const check = useMutation({
    mutationFn: (v: FormValues) => postForm<{ filename: string; cmd: string }>(
      `/${node}/schedule/check/`,
      buildCheckForm(v),
    ),
    onSuccess: (res) => {
      setCmd(res.cmd)
      setFilename(res.filename)
    },
    onError: (e) => toast.error(`Check failed: ${e.message}`),
  })

  const run = useMutation({
    mutationFn: async (v: FormValues) => {
      // always re-check right before running so the pickle matches the form
      const chk = await postForm<{ filename: string; cmd: string }>(
        `/${node}/schedule/check/`,
        buildCheckForm(v),
      )
      setCmd(chk.cmd)
      setFilename(chk.filename)
      return postForm<Record<string, unknown>>(`/${node}/schedule/run/`, {
        filename: chk.filename,
        as_json: "True",
      })
    },
    onSuccess: (res, v) => {
      if (res.status === "ok") {
        if (v.timer) {
          toast.success(String(res.flash ?? `Task #${res.task_id} added`))
          navigate("/tasks")
        } else {
          toast.success(`Spider scheduled — jobid ${res.jobid}`)
          navigate("/jobs")
        }
      } else {
        toast.error(String(res.error ?? res.alert ?? "Schedule failed"))
      }
    },
    onError: (e) => toast.error(`Run failed: ${e.message}`),
  })

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Run Spider</h2>
        <span className="font-mono text-xs text-muted-foreground">node {node}</span>
      </div>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((v) => run.mutate(v))}
          className="flex flex-col gap-4"
        >
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Target</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
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
              <FormField
                control={form.control}
                name="jobid"
                render={({ field }) => (
                  <FormItem className="sm:col-span-3">
                    <FormLabel>Job ID (optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="auto: current timestamp" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Collapsible className="group/collapse">
            <Card className="gap-3 group-data-[state=closed]/collapse:py-4">
              <CollapsibleTrigger asChild>
                <CardHeader className="flex flex-row cursor-pointer select-none items-center">
                  <CardTitle className="text-sm font-semibold">Settings & arguments</CardTitle>
                  <ChevronDown className="ml-auto size-4 text-muted-foreground" />
                </CardHeader>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <CardContent className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="USER_AGENT"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>User-Agent</FormLabel>
                        <Select
                          value={field.value || "default"}
                          onValueChange={(v) => field.onChange(v === "default" ? "" : v)}
                        >
                          <FormControl>
                            <SelectTrigger className="w-full">
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="default">default</SelectItem>
                            <SelectItem value="custom">custom (via additional)</SelectItem>
                            <SelectItem value="Chrome">Chrome</SelectItem>
                            <SelectItem value="iPhone">iPhone</SelectItem>
                            <SelectItem value="iPad">iPad</SelectItem>
                            <SelectItem value="Android">Android</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )}
                  />
                  <div className="grid grid-cols-2 gap-4">
                    <TriState form={form} name="ROBOTSTXT_OBEY" label="robots.txt" />
                    <TriState form={form} name="COOKIES_ENABLED" label="Cookies" />
                  </div>
                  <FormField
                    control={form.control}
                    name="CONCURRENT_REQUESTS"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Concurrent requests</FormLabel>
                        <FormControl>
                          <Input type="number" placeholder="default: 16" {...field} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="DOWNLOAD_DELAY"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Download delay (s)</FormLabel>
                        <FormControl>
                          <Input type="number" placeholder="default: 0" {...field} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="additional"
                    render={({ field }) => (
                      <FormItem className="sm:col-span-2">
                        <FormLabel>Additional (-d args)</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder={"-d setting=CLOSESPIDER_TIMEOUT=60\n-d arg1=val1"}
                            className="min-h-20 font-mono text-xs"
                            {...field}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>

          <Card className={cn("gap-3", !timer && "py-4")}>
            <CardHeader className="grid-cols-1">
              <div className="flex items-center">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <Timer className="size-4" /> Timer task
                </CardTitle>
                <FormField
                  control={form.control}
                  name="timer"
                  render={({ field }) => (
                    <FormItem className="ml-auto">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            </CardHeader>
            {timer && (
              <CardContent className="grid gap-4 sm:grid-cols-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem className="sm:col-span-2">
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
                    <FormItem className="sm:col-span-2">
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
                <div className="sm:col-span-4">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    Schedule (cron fields, crontab order)
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
                <div className="sm:col-span-4">
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
                </div>
                <div className="sm:col-span-4">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    Advanced (APScheduler extras — usually leave as is)
                  </p>
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
                </div>
              </CardContent>
            )}
          </Card>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={form.handleSubmit((v) => check.mutate(v))}
              disabled={check.isPending}
            >
              <TerminalSquare className="size-4" /> Check command
            </Button>
            <Button type="submit" disabled={run.isPending}>
              <Play className="size-4" /> {timer ? "Save task" : "Run spider"}
            </Button>
          </div>
        </form>
      </Form>

      {cmd && (
        <Card className="gap-2 py-4">
          <CardHeader className="!py-0">
            <CardTitle className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
              equivalent curl — {filename}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded-lg bg-background/70 p-3 font-mono text-xs leading-relaxed">
              {cmd}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function CronPreview({ spec }: { spec: Record<string, string> }) {
  // debounce the watched fields so we don't hit the API per keystroke
  const [debounced, setDebounced] = React.useState(spec)
  const key = JSON.stringify(spec)
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(spec), 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const { data } = useQuery({
    queryKey: ["cron-preview", JSON.stringify(debounced)],
    queryFn: () => postForm<{ status: string; next_runs?: string[]; message?: string }>(
      "/api/cron/preview",
      debounced,
    ),
    staleTime: 30_000,
  })

  return (
    <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <CalendarClock className="size-3.5" /> Next runs
      </p>
      {data?.status === "ok" && (data.next_runs?.length ? (
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs">
          {data.next_runs.map((t, i) => (
            <span key={t} className={i === 0 ? "text-primary" : "text-foreground/80"}>
              {t}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-1.5 font-mono text-xs text-chart-3">
          never fires — check the fields
        </p>
      ))}
      {data?.status === "error" && (
        <p className="mt-1.5 font-mono text-xs text-destructive">{data.message}</p>
      )}
      {!data && <p className="mt-1.5 font-mono text-xs text-muted-foreground">…</p>}
    </div>
  )
}

function buildCheckForm(v: FormValues): Record<string, string> {
  const out: Record<string, string> = {
    project: v.project,
    _version: v._version === LATEST ? "default: the latest version" : v._version,
    spider: v.spider,
    jobid: v.jobid,
    USER_AGENT: v.USER_AGENT === "custom" ? "" : v.USER_AGENT,
    ROBOTSTXT_OBEY: v.ROBOTSTXT_OBEY,
    COOKIES_ENABLED: v.COOKIES_ENABLED,
    CONCURRENT_REQUESTS: v.CONCURRENT_REQUESTS,
    DOWNLOAD_DELAY: v.DOWNLOAD_DELAY,
    additional: v.additional,
  }
  if (v.timer) {
    out.trigger = "cron"
    out.action = v.action
    out.name = v.name
    out.year = v.year
    out.month = v.month
    out.day = v.day
    out.week = v.week
    out.day_of_week = v.day_of_week
    out.hour = v.hour
    out.minute = v.minute
    out.second = v.second
  }
  return out
}

function TriState({
  form,
  name,
  label,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  form: any
  name: "ROBOTSTXT_OBEY" | "COOKIES_ENABLED"
  label: string
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select
            value={field.value || "default"}
            onValueChange={(v) => field.onChange(v === "default" ? "" : v)}
          >
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              <SelectItem value="default">default</SelectItem>
              <SelectItem value="True">True</SelectItem>
              <SelectItem value="False">False</SelectItem>
            </SelectContent>
          </Select>
        </FormItem>
      )}
    />
  )
}
