import * as React from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Form } from "@/components/ui/form"
import { ArgsCard } from "@/components/schedule/args-card"
import { SettingsCard } from "@/components/schedule/settings-card"
import { SummaryPanel } from "@/components/schedule/summary-panel"
import { TargetCard } from "@/components/schedule/target-card"
import { WhenCard } from "@/components/schedule/when-card"
import { api, postForm, type TaskRow } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import {
  LATEST,
  buildScheduleForm,
  type ScheduleFormValues,
} from "@/lib/schedule-payload"
import {
  ARG_KEY_RE,
  RESERVED_ARG_KEYS,
  SETTING_KEY_RE,
  SETTINGS_BY_KEY,
} from "@/lib/scrapy-settings"

const settingRow = z.object({
  key: z.string().regex(SETTING_KEY_RE, "UPPER_SNAKE key"),
  value: z.string().min(1, "value required"),
})
const argRow = z.object({
  key: z.string().regex(ARG_KEY_RE, "invalid name"),
  value: z.string().min(1, "value required"),
})

const schema = z
  .object({
    project: z.string().min(1, "Pick a project"),
    _version: z.string(),
    spider: z.string().min(1, "Pick a spider"),
    jobid: z.string(),
    nodes: z.array(z.number()).min(1, "select at least one node"),
    settings: z.array(settingRow),
    args: z.array(argRow),
    mode: z.enum(["now", "cron"]),
    name: z.string(),
    action: z.enum(["add_fire", "add", "add_pause"]),
    taskId: z.number().optional(),
    year: z.string(),
    month: z.string(),
    day: z.string(),
    week: z.string(),
    day_of_week: z.string(),
    hour: z.string(),
    minute: z.string(),
    second: z.string(),
  })
  .superRefine((v, ctx) => {
    const seenSettings = new Set<string>()
    v.settings.forEach((s, i) => {
      if (seenSettings.has(s.key))
        ctx.addIssue({ code: "custom", path: ["settings", i, "key"], message: "duplicate setting" })
      seenSettings.add(s.key)
      const def = SETTINGS_BY_KEY.get(s.key)
      if (def?.type === "int" && !/^-?\d+$/.test(s.value))
        ctx.addIssue({ code: "custom", path: ["settings", i, "value"], message: "integer required" })
      if (def?.type === "float" && Number.isNaN(Number(s.value)))
        ctx.addIssue({ code: "custom", path: ["settings", i, "value"], message: "number required" })
      if (def?.type === "bool" && s.value !== "True" && s.value !== "False")
        ctx.addIssue({ code: "custom", path: ["settings", i, "value"], message: "True or False" })
    })
    const seenArgs = new Set<string>()
    v.args.forEach((a, i) => {
      if (seenArgs.has(a.key))
        ctx.addIssue({ code: "custom", path: ["args", i, "key"], message: "duplicate argument" })
      seenArgs.add(a.key)
      if (RESERVED_ARG_KEYS.has(a.key))
        ctx.addIssue({ code: "custom", path: ["args", i, "key"], message: "reserved name" })
    })
  })

// Map a stored timer task back into Run Spider form values. settings_arguments
// is the JSON the backend persisted: a `setting` list of "KEY=VAL" strings plus
// loose arg keys; selected_nodes is the node-id list.
function taskToForm(t: TaskRow): ScheduleFormValues {
  let sa: Record<string, unknown> = {}
  try {
    sa = JSON.parse(t.settings_arguments || "{}")
  } catch {
    sa = {}
  }
  const settings = (Array.isArray(sa.setting) ? (sa.setting as string[]) : []).map((s) => {
    const i = s.indexOf("=")
    return i < 0 ? { key: s, value: "" } : { key: s.slice(0, i), value: s.slice(i + 1) }
  })
  const args = Object.entries(sa)
    .filter(([k]) => k !== "setting")
    .map(([key, value]) => ({ key, value: String(value) }))
  let nodes: number[] = []
  try {
    nodes = JSON.parse(t.selected_nodes || "[]")
  } catch {
    nodes = []
  }
  return {
    project: t.project,
    _version: t.version || LATEST,
    spider: t.spider,
    jobid: t.jobid,
    nodes: nodes.length ? nodes : [1],
    settings,
    args,
    mode: "cron",
    name: t.name || "",
    action: "add_fire",
    taskId: t.id,
    year: t.year,
    month: t.month,
    day: t.day,
    week: t.week,
    day_of_week: t.day_of_week,
    hour: t.hour,
    minute: t.minute,
    second: t.second,
  }
}

export default function SchedulePage() {
  const { node } = useNode()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const editId = params.get("taskId") ? Number(params.get("taskId")) : null

  // when editing, pull the task off the list and prefill the form once it loads
  const { data: taskList } = useQuery({
    queryKey: ["tasks", node],
    queryFn: () => api.tasks(node),
    enabled: editId != null,
  })

  const form = useForm<ScheduleFormValues>({
    resolver: zodResolver(schema),
    mode: "onChange",
    defaultValues: {
      project: params.get("project") ?? "",
      _version: params.get("version") ?? LATEST,
      spider: params.get("spider") ?? "",
      jobid: "",
      nodes: [node],
      settings: [],
      args: [],
      mode: params.get("timer") === "1" ? "cron" : "now",
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

  // keep the default node selection in sync with the topbar (only while untouched)
  React.useEffect(() => {
    if (!form.formState.dirtyFields.nodes) form.setValue("nodes", [node])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node])

  // prefill from the existing task when editing
  React.useEffect(() => {
    if (editId == null || !taskList) return
    const t = taskList.tasks.find((x) => x.id === editId)
    if (!t) return
    form.reset(taskToForm(t))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editId, taskList])

  const run = useMutation({
    mutationFn: async (v: ScheduleFormValues) => {
      const chk = await postForm<{ filename: string; cmd: string }>(
        `/${node}/schedule/check/`,
        buildScheduleForm(v),
      )
      const res = await postForm<Record<string, unknown>>(`/${node}/schedule/run/`, {
        filename: chk.filename,
        as_json: "True",
        checked_amount: String(v.nodes.length),
        ...Object.fromEntries(v.nodes.map((n) => [String(n), "on"])),
      })
      // run-now fires the first selected node; fan the rest out via the xhr endpoint
      const fanout: { node: number; ok: boolean; message?: string }[] = []
      if (v.mode === "now" && res.status === "ok" && v.nodes.length > 1) {
        for (const n of v.nodes.slice(1)) {
          try {
            const js = await postForm<Record<string, unknown>>(
              `/${n}/schedule/xhr/${encodeURIComponent(chk.filename)}/`,
              {},
            )
            fanout.push({ node: n, ok: js.status === "ok", message: String(js.message ?? "") })
          } catch (e) {
            fanout.push({ node: n, ok: false, message: (e as Error).message })
          }
        }
      }
      return { res, fanout }
    },
    onSuccess: ({ res, fanout }, v) => {
      for (const f of fanout)
        if (!f.ok) toast.error(`node ${f.node}: ${f.message || "schedule failed"}`)
      if (res.status === "ok") {
        if (v.mode === "cron") {
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
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">
          {editId != null ? `Edit Task #${editId}` : "Run Spider"}
        </h2>
        <span className="font-mono text-xs text-muted-foreground">node {node}</span>
      </div>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((v) => run.mutate(v))}
          className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]"
        >
          <div className="flex min-w-0 flex-col gap-4">
            <TargetCard node={node} />
            <SettingsCard />
            <ArgsCard />
            <WhenCard />
          </div>
          <SummaryPanel pending={run.isPending} />
        </form>
      </Form>
    </div>
  )
}
