import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import {
  CalendarClock,
  ChevronDown,
  Crosshair,
  Layers,
  Pencil,
  Play,
  Save,
  TerminalSquare,
  Trash2,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
import { NodeMultiSelect } from "@/components/node-multi-select"
import { ProjectComboBox } from "@/components/project-combobox"
import { api, getJSON, type JobGroup } from "@/lib/api"
import { useConfirm } from "@/components/confirm-dialog"
import { useNode } from "@/lib/node-context"
import { LATEST } from "@/lib/schedule-payload"

const schema = z.object({
  name: z.string().min(1, "Name the group"),
  project: z.string().min(1, "Pick a project"),
  _version: z.string(),
  spiders: z.array(z.string()).min(1, "Pick at least one spider"),
  nodes: z.array(z.number()).min(1, "Pick at least one node"),
  settings: z.array(z.object({ key: z.string(), value: z.string() })),
  args: z.array(z.object({ key: z.string(), value: z.string() })),
})
type GroupFormValues = z.infer<typeof schema>

const EMPTY = (node: number): GroupFormValues => ({
  name: "",
  project: "",
  _version: LATEST,
  spiders: [],
  nodes: [node],
  settings: [],
  args: [],
})

function toRecord(v: GroupFormValues): Record<string, unknown> {
  return {
    name: v.name.trim(),
    project: v.project,
    version: v._version === LATEST ? "" : v._version,
    spiders: v.spiders,
    nodes: v.nodes,
    settings: v.settings.filter((s) => s.key && s.value),
    args: Object.fromEntries(v.args.filter((a) => a.key && a.value).map((a) => [a.key, a.value])),
  }
}

export default function GroupsPage() {
  const { node } = useNode()
  const qc = useQueryClient()
  const { confirm, dialog } = useConfirm()
  const [editingId, setEditingId] = React.useState<number | null>(null)

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(schema),
    mode: "onChange",
    defaultValues: EMPTY(node),
  })
  const project = form.watch("project")
  const version = form.watch("_version")
  const selected = form.watch("spiders")

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

  const { data: groupsData } = useQuery({ queryKey: ["groups"], queryFn: api.listGroups })
  const groups = groupsData?.groups ?? []

  const toggle = (sp: string) =>
    form.setValue(
      "spiders",
      selected.includes(sp) ? selected.filter((s) => s !== sp) : [...selected, sp],
      { shouldValidate: true },
    )

  const reset = () => {
    setEditingId(null)
    form.reset(EMPTY(node))
  }

  const save = useMutation({
    mutationFn: (v: GroupFormValues) =>
      editingId ? api.updateGroup(editingId, toRecord(v)) : api.createGroup(toRecord(v)),
    onSuccess: (res) => {
      if (res.status === "ok") {
        toast.success(editingId ? "Group updated" : `Saved group "${res.group?.name}"`)
        reset()
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
      if (res.scheduled > 0) toast.success(`Fired ${res.scheduled}/${res.total} job(s)`)
      else toast.error("Nothing fired")
    },
    onError: (e) => toast.error(`Fire failed: ${e.message}`),
  })

  const edit = (g: JobGroup) => {
    setEditingId(g.id)
    form.reset({
      name: g.name,
      project: g.project,
      _version: g.version || LATEST,
      spiders: g.spiders,
      nodes: g.nodes.length ? g.nodes : [node],
      settings: g.settings,
      args: Object.entries(g.args).map(([key, value]) => ({ key, value })),
    })
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  const remove = async (g: JobGroup) => {
    if (
      await confirm({
        title: `Delete group "${g.name}"?`,
        description: "The saved group is removed. Existing jobs/tasks are untouched.",
        confirmLabel: "Delete",
        destructive: true,
      })
    ) {
      await api.deleteGroup(g.id)
      if (editingId === g.id) reset()
      qc.invalidateQueries({ queryKey: ["groups"] })
    }
  }

  const [schedFor, setSchedFor] = React.useState<JobGroup | null>(null)

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Layers className="size-5" /> Groups
        </h2>
        <span className="font-mono text-xs text-muted-foreground">node {node}</span>
      </div>

      {/* builder */}
      <Form {...form}>
        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Crosshair className="size-4" />
                {editingId ? "Edit group" : "New group"}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="grid gap-2">
                  <Label htmlFor="grp-name">Name</Label>
                  <Input id="grp-name" placeholder="e.g. nightly-item" {...form.register("name")} />
                </div>
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
                  <Label>Spiders ({selected.length})</Label>
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
                  <div className="grid max-h-56 grid-cols-2 gap-1 overflow-y-auto rounded-lg border border-border p-2 sm:grid-cols-3">
                    {spiders.map((sp) => (
                      <label
                        key={sp}
                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 font-mono text-xs hover:bg-secondary/50"
                      >
                        <Checkbox checked={selected.includes(sp)} onCheckedChange={() => toggle(sp)} />
                        <span className="truncate">{sp}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-2">
                <Label>Nodes</Label>
                <NodeMultiSelect
                  value={form.watch("nodes")}
                  onChange={(n) => form.setValue("nodes", n, { shouldValidate: true })}
                />
              </div>
            </CardContent>
          </Card>

          <SettingsCard />
          <ArgsCard />

          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending}>
              <Save className="size-4" /> {editingId ? "Update group" : "Save group"}
            </Button>
            {editingId && (
              <Button type="button" variant="outline" onClick={reset}>
                <X className="size-4" /> Cancel
              </Button>
            )}
          </div>
        </form>
      </Form>

      {/* saved groups */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Saved groups</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {groups.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No groups yet — build one above.
            </p>
          )}
          {groups.map((g) => (
            <div key={g.id} className="rounded-lg border border-border bg-secondary/20 px-3 py-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-medium">{g.name}</span>
                <span className="font-mono text-xs text-muted-foreground">
                  {g.project}
                  {g.version ? `@${g.version}` : ""} · {g.spiders.length} spider(s) · nodes{" "}
                  {g.nodes.join(",")}
                </span>
                <div className="ml-auto flex items-center gap-1">
                  <Button type="button" size="sm" className="h-7" disabled={fire.isPending} onClick={() => fire.mutate(g.id)}>
                    <Play className="size-3.5" /> Fire now
                  </Button>
                  <Button type="button" size="sm" variant="outline" className="h-7" onClick={() => setSchedFor(g)}>
                    <CalendarClock className="size-3.5" /> Schedule
                  </Button>
                  <Button type="button" variant="ghost" size="icon" className="size-7" onClick={() => edit(g)} aria-label="Edit">
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 text-destructive hover:text-destructive"
                    onClick={() => remove(g)}
                    aria-label="Delete"
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
                    {`curl -X POST '${window.location.origin}${g.fire_path}' \\\n  -H 'Authorization: Bearer sdw_…'`}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            </div>
          ))}
        </CardContent>
      </Card>

      <ScheduleDialog group={schedFor} onClose={() => setSchedFor(null)} qc={qc} />
      {dialog}
    </div>
  )
}

function ScheduleDialog({
  group,
  onClose,
  qc,
}: {
  group: JobGroup | null
  onClose: () => void
  qc: ReturnType<typeof useQueryClient>
}) {
  const [cron, setCron] = React.useState({
    minute: "0",
    hour: "*",
    day: "*",
    month: "*",
    day_of_week: "*",
  })
  const [action, setAction] = React.useState("add")

  const mut = useMutation({
    mutationFn: () =>
      api.scheduleSavedGroup(group!.id, { ...cron, year: "*", week: "*", second: "0", action }),
    onSuccess: (res) => {
      if (res.scheduled > 0) toast.success(`Created ${res.scheduled} timer task(s)`)
      else toast.error("Nothing scheduled")
      qc.invalidateQueries({ queryKey: ["tasks"] })
      onClose()
    },
    onError: (e) => toast.error(`Schedule failed: ${e.message}`),
  })

  return (
    <Dialog open={!!group} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Schedule "{group?.name}"</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Creates one timer task per spider ({group?.spiders.length}). Manage them on the Timer Tasks
          page.
        </p>
        <div className="grid grid-cols-5 gap-2">
          {(["minute", "hour", "day", "month", "day_of_week"] as const).map((k) => (
            <div key={k} className="grid gap-1">
              <Label className="text-[10px] uppercase text-muted-foreground">
                {k === "day_of_week" ? "dow" : k}
              </Label>
              <Input
                className="h-8 text-center font-mono text-xs"
                value={cron[k]}
                onChange={(e) => setCron((c) => ({ ...c, [k]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div className="grid gap-1">
          <Label className="text-xs">On create</Label>
          <Select value={action} onValueChange={setAction}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="add">schedule (active)</SelectItem>
              <SelectItem value="add_pause">create paused</SelectItem>
              <SelectItem value="add_fire">schedule + run now</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            <CalendarClock className="size-4" /> Create tasks
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
