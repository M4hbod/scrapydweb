import * as React from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, Code2, FolderGit2, Play, Plus, Rocket, Settings2, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Skeleton } from "@/components/ui/skeleton"
import { api, getJSON, postJSON, type DeployNodeResult, type Project } from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { useConfirm } from "@/components/confirm-dialog"
import { ProjectDialog } from "@/components/project-dialog"

const LATEST = "default: the latest version"

export default function ProjectsPage() {
  const { node } = useNode()
  const qc = useQueryClient()
  const [creating, setCreating] = React.useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ["projects", node],
    queryFn: () => getJSON<{ projects?: string[]; status: string }>(`/${node}/api/listprojects/`),
  })
  const { data: registered } = useQuery({ queryKey: ["projects"], queryFn: api.listProjects })

  const regByName = new Map((registered?.projects ?? []).map((p) => [p.name, p]))
  const names = Array.from(
    new Set([...(data?.projects ?? []), ...(registered?.projects ?? []).map((p) => p.name)]),
  ).sort((a, b) => a.localeCompare(b))

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Projects</h2>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-muted-foreground">
            {names.length} projects · node {node}
          </span>
          <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setCreating(true)}>
            <Plus className="size-3.5" /> Create project
          </Button>
        </div>
      </div>
      {isLoading && <Skeleton className="h-64 rounded-xl" />}
      {!isLoading && names.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <FolderGit2 className="size-7 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No projects yet.</p>
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Create a project
            </Button>
          </CardContent>
        </Card>
      )}
      {names.map((p) => (
        <ProjectCard key={p} node={node} project={p} registered={regByName.get(p) ?? null} />
      ))}
      {creating && (
        <ProjectDialog
          project={null}
          onClose={() => setCreating(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["projects"] })}
        />
      )}
    </div>
  )
}

function ProjectCard({
  node,
  project,
  registered,
}: {
  node: number
  project: string
  registered: Project | null
}) {
  const qc = useQueryClient()
  const { confirm: confirmDialog, dialog: confirmUI } = useConfirm()
  const [open, setOpen] = React.useState(false)
  const [configuring, setConfiguring] = React.useState(false)

  const canDeploy = registered && (registered.deploy_source === "git" || registered.deploy_source === "webhook")
  const deploy = useMutation({
    mutationFn: () => api.deployProject(registered!.id),
    onSuccess: (res) => {
      for (const r of (res.results as DeployNodeResult[] | undefined) ?? [])
        if (r.status !== "ok") toast.error(`node ${r.node}: ${r.message || "failed"}`)
      if (res.status === "ok")
        toast.success(`Deployed ${res.project} (${res.version})`)
      else toast.error(String(res.message ?? "Deploy failed"))
      qc.invalidateQueries({ queryKey: ["versions", node, project] })
    },
    onError: (e) => toast.error(`Deploy failed: ${e.message}`),
  })

  const { data: versions, isLoading } = useQuery({
    queryKey: ["versions", node, project],
    queryFn: () =>
      getJSON<{ versions?: string[] }>(`/${node}/api/listversions/${encodeURIComponent(project)}/`),
    enabled: open,
  })

  const del = useMutation({
    mutationFn: ({ version }: { version?: string }) =>
      postJSON<{ status: string }>(
        version
          ? `/${node}/api/delversion/${encodeURIComponent(project)}/${encodeURIComponent(version)}/`
          : `/${node}/api/delproject/${encodeURIComponent(project)}/`,
      ),
    onSuccess: (res, { version }) => {
      if (res.status === "ok") toast.success(version ? `Version ${version} deleted` : `Project ${project} deleted`)
      else toast.error(`Delete failed: ${JSON.stringify(res).slice(0, 150)}`)
      qc.invalidateQueries({ queryKey: ["projects", node] })
      qc.invalidateQueries({ queryKey: ["versions", node, project] })
    },
    onError: (e) => toast.error(`Delete failed: ${e.message}`),
  })

  const prune = useMutation({
    mutationFn: async () => {
      const all = versions?.versions ?? []
      const old = all.slice(0, -1) // scrapyd lists ascending -> keep the last (latest)
      for (const v of old)
        await postJSON(`/${node}/api/delversion/${encodeURIComponent(project)}/${encodeURIComponent(v)}/`)
      return old.length
    },
    onSuccess: (n) => {
      toast.success(`Deleted ${n} old version${n === 1 ? "" : "s"}`)
      qc.invalidateQueries({ queryKey: ["versions", node, project] })
    },
    onError: (e) => toast.error(`Prune failed: ${e.message}`),
  })

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="gap-3">
        <CardHeader className="grid-cols-1">
          <div className="flex items-center gap-3">
            <FolderGit2 className="size-4 text-muted-foreground" />
            <span className="font-medium">{project}</span>
            {registered && (
              <Badge variant="secondary" className="text-[10px]">
                {registered.deploy_source}
              </Badge>
            )}
            <div className="ml-auto flex items-center gap-1.5">
            {canDeploy && (
              <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs"
                disabled={deploy.isPending} onClick={() => deploy.mutate()}>
                <Rocket className="size-3" /> {deploy.isPending ? "Deploying…" : "Deploy"}
              </Button>
            )}
            <Button asChild variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
              <Link to={`/schedule?project=${encodeURIComponent(project)}`}>
                <Play className="size-3" /> Run
              </Link>
            </Button>
            <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs"
              onClick={() => setConfiguring(true)}>
              <Settings2 className="size-3" /> Configure
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 text-xs text-destructive hover:text-destructive"
              onClick={async () =>
                (await confirmDialog({
                  title: `Delete project "${project}"?`,
                  description: `All versions on node ${node} will be removed from scrapyd.`,
                  confirmLabel: "Delete project",
                  destructive: true,
                })) && del.mutate({})
              }
            >
              <Trash2 className="size-3" /> Delete
            </Button>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="icon" className="size-7">
                  <ChevronDown
                    className={`size-4 transition-transform ${open ? "rotate-180" : ""}`}
                  />
                </Button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="flex flex-col gap-2">
            {isLoading && <Skeleton className="h-16 rounded-lg" />}
            {(versions?.versions ?? []).length > 1 && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 self-start gap-1.5 text-xs text-destructive hover:text-destructive"
                disabled={prune.isPending}
                onClick={async () =>
                  (await confirmDialog({
                    title: `Delete old versions of "${project}"?`,
                    description: `Keeps only the latest version on node ${node}; removes the other ${(versions?.versions ?? []).length - 1}.`,
                    confirmLabel: "Delete old versions",
                    destructive: true,
                  })) && prune.mutate()
                }
              >
                <Trash2 className="size-3" /> {prune.isPending ? "Deleting…" : "Delete old versions (keep latest)"}
              </Button>
            )}
            {(versions?.versions ?? []).map((v) => (
              <VersionRow key={v} node={node} project={project} version={v} onDelete={() => del.mutate({ version: v })} />
            ))}
            {versions && (versions.versions ?? []).length === 0 && (
              <p className="text-sm text-muted-foreground">No versions.</p>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
      {configuring && (
        <ProjectDialog
          project={registered}
          defaultName={project}
          onClose={() => setConfiguring(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["projects"] })}
        />
      )}
      {confirmUI}
    </Collapsible>
  )
}

function VersionRow({
  node,
  project,
  version,
  onDelete,
}: {
  node: number
  project: string
  version: string
  onDelete: () => void
}) {
  const [showSpiders, setShowSpiders] = React.useState(false)
  const { confirm: confirmDialog, dialog: confirmUI } = useConfirm()
  const { data: spiders, isLoading: spidersLoading } = useQuery({
    queryKey: ["spiders", node, project, version],
    queryFn: () =>
      getJSON<{ spiders?: string[] }>(
        `/${node}/api/listspiders/${encodeURIComponent(project)}/${encodeURIComponent(version)}/`,
      ),
    enabled: showSpiders,
  })

  const ts = Number(version)
  const readable =
    Number.isInteger(ts) && ts > 1_000_000_000
      ? new Date(ts * 1000).toISOString().slice(0, 19)
      : null

  return (
    <div className="rounded-lg border border-border bg-secondary/30 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs font-medium">{version}</span>
        {readable && (
          <span className="font-mono text-[11px] text-muted-foreground">({readable})</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button asChild variant="ghost" size="sm" className="h-6 gap-1 text-xs">
            <Link to={`/code/${encodeURIComponent(project)}/${encodeURIComponent(version)}`}>
              <Code2 className="size-3" /> code
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs"
            onClick={() => setShowSpiders((s) => !s)}
          >
            spiders
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-6 text-destructive hover:text-destructive"
            aria-label={`Delete version ${version}`}
            onClick={async () =>
              (await confirmDialog({
                title: `Delete version "${version}"?`,
                description: `${project} on node ${node} — this version's egg is removed from scrapyd.`,
                confirmLabel: "Delete version",
                destructive: true,
              })) && onDelete()
            }
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      </div>
      {showSpiders && (
        <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border pt-2">
          {spidersLoading &&
            [0, 1, 2].map((i) => <Skeleton key={i} className="h-[22px] w-16 rounded-full" />)}
          {(spiders?.spiders ?? []).map((s) => (
            <Badge key={s} variant="outline" asChild className="cursor-pointer hover:border-primary/40">
              <Link
                to={`/schedule?project=${encodeURIComponent(project)}&spider=${encodeURIComponent(s)}${
                  version === LATEST ? "" : `&version=${encodeURIComponent(version)}`
                }`}
              >
                {s}
              </Link>
            </Badge>
          ))}
          {spiders && (spiders.spiders ?? []).length === 0 && (
            <span className="text-xs text-muted-foreground">no spiders</span>
          )}
        </div>
      )}
      {confirmUI}
    </div>
  )
}
