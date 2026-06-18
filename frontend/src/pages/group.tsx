import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { ChevronDown, Crosshair, Layers, Play, Save, TerminalSquare, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Form } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ArgsCard } from "@/components/schedule/args-card"
import { SettingsCard } from "@/components/schedule/settings-card"
import { WhenCard } from "@/components/schedule/when-card"
import { NodeMultiSelect } from "@/components/node-multi-select"
import { ProjectComboBox } from "@/components/project-combobox"
import { api, getJSON } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { LATEST, backendGroupCurl } from "@/lib/schedule-payload"

const schema = z.object({
  project: z.string().min(1, "Pick a project"),
  _version: z.string(),
  spiders: z.array(z.string()).min(1, "Pick at least one spider"),
  nodes: z.array(z.number()).min(1, "Pick at least one node"),
  jobid: z.string(),
  settings: z.array(z.object({ key: z.string(), value: z.string() })),
  args: z.array(z.object({ key: z.string(), value: z.string() })),
  mode: z.enum(["now", "cron"]),
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
type GroupFormValues = z.infer<typeof schema>

// the JSON body POSTed to /{node}/schedule/group/ (shared by submit + curl preview)
function toBody(v: GroupFormValues): Record<string, unknown> {
  const body: Record<string, unknown> = {
    project: v.project,
    _version: v._version,
    spiders: v.spiders,
    nodes: v.nodes,
    jobid: v.jobid,
    settings: v.settings.filter((s) => s.key && s.value),
    args: Object.fromEntries(v.args.filter((a) => a.key && a.value).map((a) => [a.key, a.value])),
  }
  if (v.mode === "cron")
    Object.assign(body, {
      trigger: "cron",
      action: v.action,
      name: v.name,
      year: v.year,
      month: v.month,
      day: v.day,
      week: v.week,
      day_of_week: v.day_of_week,
      hour: v.hour,
      minute: v.minute,
      second: v.second,
    })
  return body
}

export default function GroupPage() {
  const { node } = useNode()
  const navigate = useNavigate()

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(schema),
    mode: "onChange",
    defaultValues: {
      project: "",
      _version: LATEST,
      spiders: [],
      nodes: [node],
      jobid: "",
      settings: [],
      args: [],
      mode: "now",
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
  const selected = form.watch("spiders")
  const mode = form.watch("mode")

  const { data: versions } = useQuery({
    queryKey: ["listversions", node, project],
    queryFn: () => getJSON<{ versions?: string[] }>(`/${node}/api/listversions/${encodeURIComponent(project)}/`),
    enabled: !!project,
  })
  const { data: spiderData, isFetching: spidersLoading } = useQuery({
    queryKey: ["listspiders", node, project, version],
    queryFn: () =>
      getJSON<{ spiders?: string[] }>(
        `/${node}/api/listspiders/${encodeURIComponent(project)}/${encodeURIComponent(version)}/`,
      ),
    enabled: !!project,
  })
  const spiders = spiderData?.spiders ?? []
  const allSelected = spiders.length > 0 && selected.length === spiders.length

  const toggle = (sp: string) =>
    form.setValue(
      "spiders",
      selected.includes(sp) ? selected.filter((s) => s !== sp) : [...selected, sp],
      { shouldValidate: true },
    )

  const run = useMutation({
    mutationFn: (v: GroupFormValues) => api.scheduleGroup(node, toBody(v)),
    onSuccess: (res, v) => {
      for (const r of res.results)
        if (r.status !== "ok")
          toast.error(`${r.spider}: ${r.message || "failed"}`)
      if (res.scheduled > 0) {
        if (v.mode === "cron") {
          toast.success(`Created ${res.scheduled}/${res.total} timer task(s)`)
          navigate("/tasks")
        } else {
          toast.success(`Scheduled ${res.scheduled}/${res.total} job(s)`)
          navigate("/jobs")
        }
      } else {
        toast.error("Nothing scheduled")
      }
    },
    onError: (e) => toast.error(`Run group failed: ${e.message}`),
  })

  // saved groups: persist the current config, then fire by id (curl-friendly)
  const qc = useQueryClient()
  const [groupName, setGroupName] = React.useState("")
  const { data: groupsData } = useQuery({ queryKey: ["groups"], queryFn: api.listGroups })
  const groups = groupsData?.groups ?? []

  const save = useMutation({
    mutationFn: () => {
      const v = form.getValues()
      return api.createGroup({
        name: groupName.trim(),
        project: v.project,
        version: v._version === LATEST ? "" : v._version,
        spiders: v.spiders,
        nodes: v.nodes,
        settings: v.settings.filter((s) => s.key && s.value),
        args: Object.fromEntries(
          v.args.filter((a) => a.key && a.value).map((a) => [a.key, a.value]),
        ),
      })
    },
    onSuccess: (res) => {
      if (res.status === "ok") {
        toast.success(`Saved group "${res.group?.name}"`)
        setGroupName("")
        qc.invalidateQueries({ queryKey: ["groups"] })
      } else {
        toast.error(res.message || "Save failed")
      }
    },
    onError: (e) => toast.error(`Save failed: ${e.message}`),
  })

  const fire = useMutation({
    mutationFn: (id: number) => api.fireGroup(id),
    onSuccess: (res) => {
      for (const r of res.results)
        if (r.status !== "ok") toast.error(`${r.spider}: ${r.message || "failed"}`)
      if (res.scheduled > 0) toast.success(`Fired ${res.scheduled}/${res.total} job(s)`)
      else toast.error("Nothing fired")
    },
    onError: (e) => toast.error(`Fire failed: ${e.message}`),
  })

  const del = useMutation({
    mutationFn: (id: number) => api.deleteGroup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["groups"] }),
  })

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Layers className="size-5" /> Run Group
        </h2>
        <span className="font-mono text-xs text-muted-foreground">node {node}</span>
      </div>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((v) => run.mutate(v))}
          className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]"
        >
          <div className="flex min-w-0 flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <Crosshair className="size-4" /> Target
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-2">
                    <Label>Project</Label>
                    <ProjectComboBox
                      node={node}
                      value={project}
                      onChange={(v) => {
                        form.setValue("project", v)
                        form.setValue("_version", LATEST)
                        form.setValue("spiders", [])
                      }}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Version</Label>
                    <Select
                      value={version}
                      onValueChange={(v) => {
                        form.setValue("_version", v)
                        form.setValue("spiders", [])
                      }}
                      disabled={!project}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={LATEST}>{LATEST}</SelectItem>
                        {(versions?.versions ?? []).map((v) => (
                          <SelectItem key={v} value={v}>
                            {v}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid gap-2">
                  <div className="flex items-center justify-between">
                    <Label>Spiders</Label>
                    {spiders.length > 0 && (
                      <button
                        type="button"
                        className="text-xs text-muted-foreground hover:text-foreground"
                        onClick={() =>
                          form.setValue("spiders", allSelected ? [] : [...spiders], {
                            shouldValidate: true,
                          })
                        }
                      >
                        {allSelected ? "Clear all" : "Select all"}
                      </button>
                    )}
                  </div>
                  {!project ? (
                    <p className="text-sm text-muted-foreground">Pick a project first.</p>
                  ) : spidersLoading ? (
                    <p className="text-sm text-muted-foreground">Loading spiders…</p>
                  ) : spiders.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No spiders for this version.</p>
                  ) : (
                    <div className="grid max-h-64 grid-cols-2 gap-1 overflow-y-auto rounded-lg border border-border p-2">
                      {spiders.map((sp) => (
                        <label
                          key={sp}
                          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 font-mono text-xs hover:bg-secondary/50"
                        >
                          <Checkbox
                            checked={selected.includes(sp)}
                            onCheckedChange={() => toggle(sp)}
                          />
                          <span className="truncate">{sp}</span>
                        </label>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {selected.length} selected — same version, settings and arguments go to each.
                  </p>
                </div>

                <div className="grid gap-2">
                  <Label>Deploy to nodes</Label>
                  <NodeMultiSelect
                    value={form.watch("nodes")}
                    onChange={(n) => form.setValue("nodes", n, { shouldValidate: true })}
                  />
                </div>

                <div className="grid gap-2">
                  <Label htmlFor="grp-jobid">Job id prefix (optional)</Label>
                  <Input
                    id="grp-jobid"
                    className="font-mono"
                    placeholder="auto: timestamp"
                    {...form.register("jobid")}
                  />
                  <p className="text-xs text-muted-foreground">
                    Each job id becomes <code>&lt;prefix&gt;_&lt;spider&gt;</code>.
                  </p>
                </div>
              </CardContent>
            </Card>

            <SettingsCard />
            <ArgsCard />
            <WhenCard />
          </div>

          <Card className="lg:sticky lg:top-4">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Summary</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <Row k="Project" v={project || "—"} />
              <Row k="Version" v={version === LATEST ? "latest" : version} />
              <Row k="Spiders" v={String(selected.length)} />
              <Row k="Nodes" v={String(form.watch("nodes").length)} />
              <Row k="When" v={mode === "cron" ? "timer" : "now"} />

              <Collapsible>
                <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                  <TerminalSquare className="size-3.5" /> Equivalent curl
                  <ChevronDown className="size-3" />
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-2">
                  <pre className="overflow-auto rounded-lg bg-background/70 p-2.5 font-mono text-[11px] leading-relaxed">
                    {backendGroupCurl(
                      form.watch("nodes")?.[0] ?? node,
                      toBody(form.watch() as GroupFormValues),
                      window.location.origin,
                    )}
                  </pre>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    hits the scrapydweb backend; log in first (POST /api/auth/login) and pass the
                    session cookie
                  </p>
                </CollapsibleContent>
              </Collapsible>

              <Button type="submit" disabled={run.isPending} className="mt-2">
                {run.isPending
                  ? "Scheduling…"
                  : mode === "cron"
                    ? `Create ${selected.length} task(s)`
                    : `Run ${selected.length} spider(s)`}
              </Button>

              <div className="flex gap-2 pt-1">
                <Input
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  placeholder="group name"
                  className="h-8 text-xs"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 shrink-0"
                  disabled={!groupName.trim() || !project || selected.length === 0 || save.isPending}
                  onClick={() => save.mutate()}
                >
                  <Save className="size-3.5" /> Save
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Save this set as a reusable group, then fire it by id via curl.
              </p>
            </CardContent>
          </Card>
        </form>
      </Form>

      {groups.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Saved groups</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {groups.map((g) => (
              <div key={g.id} className="rounded-lg border border-border bg-secondary/20 px-3 py-2">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-medium">{g.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {g.project} · {g.spiders.length} spider(s) · nodes {g.nodes.join(",")}
                  </span>
                  <div className="ml-auto flex items-center gap-1">
                    <Button
                      type="button"
                      size="sm"
                      className="h-7"
                      disabled={fire.isPending}
                      onClick={() => fire.mutate(g.id)}
                    >
                      <Play className="size-3.5" /> Fire now
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-7 text-destructive hover:text-destructive"
                      onClick={() => del.mutate(g.id)}
                      aria-label="Delete group"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
                <Collapsible>
                  <CollapsibleTrigger className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                    <TerminalSquare className="size-3.5" /> Fire curl
                    <ChevronDown className="size-3" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-1.5">
                    <pre className="overflow-auto rounded-lg bg-background/70 p-2.5 font-mono text-[11px] leading-relaxed">
                      {`curl -X POST '${window.location.origin}${g.fire_path}' -b cookies.txt`}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-mono text-xs">{v}</span>
    </div>
  )
}
