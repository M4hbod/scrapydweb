import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Copy,
  FileArchive,
  FolderGit2,
  GitBranch,
  Pencil,
  Plus,
  Rocket,
  UploadCloud,
  Webhook,
  Workflow,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { NodeMultiSelect } from "@/components/node-multi-select"
import { ProjectComboBox } from "@/components/project-combobox"
import { ProjectDialog } from "@/components/project-dialog"
import {
  api,
  getJSON,
  type DeployNodeResult,
  type DeployRecord,
  type Project,
} from "@/lib/api"
import { fmtDateTime } from "@/lib/datetime"
import { useNode } from "@/lib/node-context"
import { cn } from "@/lib/utils"

interface FolderEntry {
  folder: string
  project: string
  modified: string
}

interface FoldersResponse {
  status: string
  projects_dir: string
  latest_folder: string
  folders: FolderEntry[]
}

function nowVersion() {
  // mirror legacy get_now_string(): 2026-06-06T22_30_36
  return new Date().toISOString().slice(0, 19).replace(/:/g, "_")
}

function toastNodeResults(results: DeployNodeResult[] | undefined) {
  for (const r of results ?? []) {
    if (r.status !== "ok")
      toast.error(`node ${r.node} (${r.server}): ${r.message || `status ${r.status_code}`}`)
  }
}

export default function DeployPage() {
  const { node } = useNode()
  const navigate = useNavigate()
  const [file, setFile] = React.useState<File | null>(null)
  const [folder, setFolder] = React.useState("")
  const [project, setProject] = React.useState("")
  const [version, setVersion] = React.useState(nowVersion)
  const [dragOver, setDragOver] = React.useState(false)
  const [nodes, setNodes] = React.useState<number[]>([node])

  // keep the default selection in sync when the topbar node changes
  React.useEffect(() => setNodes([node]), [node])

  const { data: scan, isLoading } = useQuery({
    queryKey: ["deploy-folders", node],
    queryFn: () => getJSON<FoldersResponse>(`/api/${node}/deploy/folders/`),
  })

  const qc = useQueryClient()
  const deploy = useMutation({
    mutationFn: async (src: { kind: "file"; file: File } | { kind: "folder"; folder: string }) => {
      const fd = new FormData()
      fd.set("as_json", "True")
      fd.set("project", project)
      fd.set("version", version)
      fd.set("nodes", nodes.join(","))
      if (src.kind === "file") fd.set("file", src.file)
      else fd.set("folder", src.folder)
      const res = await fetch(`/${node}/deploy/upload/`, { method: "POST", body: fd })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      return res.json() as Promise<Record<string, unknown>>
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["deploy-history"] })
      if (res.status === "ok") {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        toast.success(
          `Deployed ${res.project} (${res.version})${res.overall === "partial" ? " — some nodes failed" : ""}`,
        )
        navigate(`/schedule?project=${encodeURIComponent(String(res.project))}`)
      } else {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        toast.error(`${res.alert ?? "Deploy failed"}: ${res.text ?? res.message ?? ""}`)
      }
    },
    onError: (e) => toast.error(`Deploy failed: ${e.message}`),
  })

  const pickFolder = (f: FolderEntry) => {
    setFolder(f.folder)
    setProject((p) => p || f.project)
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Deploy Project</h2>
        <span className="font-mono text-xs text-muted-foreground">node {node}</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Target</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label>Project</Label>
            <ProjectComboBox node={node} value={project} onChange={setProject} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dp-version">Version</Label>
            <Input
              id="dp-version"
              className="font-mono"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              disabled={!project}
            />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>Deploy to nodes</Label>
            <NodeMultiSelect value={nodes} onChange={setNodes} />
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="folder">
        <TabsList>
          <TabsTrigger value="folder">
            <FolderGit2 className="size-4" /> Server folder
          </TabsTrigger>
          <TabsTrigger value="upload">
            <UploadCloud className="size-4" /> Upload egg / archive
          </TabsTrigger>
          <TabsTrigger value="git">
            <GitBranch className="size-4" /> From git
          </TabsTrigger>
          <TabsTrigger value="auto">
            <Webhook className="size-4" /> Auto-deploy
          </TabsTrigger>
          <TabsTrigger value="ci">
            <Workflow className="size-4" /> CI / GitHub
          </TabsTrigger>
        </TabsList>

        <TabsContent value="folder">
          <Card>
            <CardHeader>
              <CardTitle className="font-mono text-xs text-muted-foreground">
                {scan?.projects_dir ?? "…"}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {isLoading && <Skeleton className="h-24 rounded-lg" />}
              {scan && scan.folders.length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  No scrapy projects found (folders containing scrapy.cfg).
                </p>
              )}
              {scan?.folders.map((f) => (
                <button
                  key={f.folder}
                  type="button"
                  onClick={() => pickFolder(f)}
                  className={cn(
                    "flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2.5 text-left transition-colors",
                    folder === f.folder
                      ? "border-primary/50 bg-accent/40"
                      : "border-border bg-secondary/30 hover:border-primary/30",
                  )}
                >
                  <FolderGit2 className="size-4 text-muted-foreground" />
                  <span className="font-medium">{f.folder}</span>
                  <span className="font-mono text-xs text-muted-foreground">→ {f.project}</span>
                  {f.folder === scan.latest_folder && (
                    <Badge variant="secondary" className="text-[10px]">
                      latest
                    </Badge>
                  )}
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                    {fmtDateTime(f.modified)}
                  </span>
                </button>
              ))}
              <Button
                className="mt-2 self-start"
                disabled={!folder || nodes.length === 0 || deploy.isPending}
                onClick={() => deploy.mutate({ kind: "folder", folder })}
              >
                <Rocket className="size-4" />
                {deploy.isPending ? "Building egg…" : `Deploy ${folder || "folder"}`}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="upload">
          <Card>
            <CardContent className="flex flex-col gap-3">
              <label
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(true)
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragOver(false)
                  const f = e.dataTransfer.files[0]
                  if (f) setFile(f)
                }}
                className={cn(
                  "flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
                  dragOver ? "border-primary bg-accent/30" : "border-border bg-secondary/20",
                )}
              >
                <FileArchive className="size-6 text-muted-foreground" />
                {file ? (
                  <span className="font-mono text-sm">{file.name}</span>
                ) : (
                  <>
                    <span className="text-sm">Drop an egg / zip / tar.gz here, or click to browse</span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      archives are unpacked and built into an egg server-side
                    </span>
                  </>
                )}
                <input
                  type="file"
                  accept=".egg,.zip,.tar.gz,.gz"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <Button
                className="self-start"
                disabled={!file || nodes.length === 0 || deploy.isPending}
                onClick={() => file && deploy.mutate({ kind: "file", file })}
              >
                <Rocket className="size-4" />
                {deploy.isPending ? "Deploying…" : "Deploy file"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="git">
          <GitDeployCard node={node} nodes={nodes} />
        </TabsContent>

        <TabsContent value="auto">
          <AutoDeployCard />
        </TabsContent>

        <TabsContent value="ci">
          <CiTemplateCard />
        </TabsContent>
      </Tabs>

      <RecentDeploysCard />
    </div>
  )
}

function GitDeployCard({ node, nodes }: { node: number; nodes: number[] }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [repo, setRepo] = React.useState("")
  const [ref, setRef] = React.useState("main")
  const [token, setToken] = React.useState("")
  const [project, setProject] = React.useState("")
  const [version, setVersion] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const submit = async () => {
    setError("")
    setBusy(true)
    try {
      const res = await api.deployGit({ repo, ref, token, project, version, node, nodes })
      qc.invalidateQueries({ queryKey: ["deploy-history"] })
      if (res.status === "ok") {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        toast.success(`Deployed ${res.project} (${res.version}) from git`)
        navigate(`/schedule?project=${encodeURIComponent(String(res.project))}`)
      } else {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        setError(String(res.message ?? res.text ?? res.alert ?? "Deploy failed"))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="git-repo">Repository (https)</Label>
          <Input
            id="git-repo"
            placeholder="https://github.com/you/your-scrapy-project"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-ref">Branch / tag</Label>
          <Input id="git-ref" value={ref} onChange={(e) => setRef(e.target.value)}
                 className="font-mono text-xs" />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-token">Access token (private repos)</Label>
          <Input
            id="git-token"
            type="password"
            autoComplete="off"
            placeholder="optional"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-2">
          <Label>Project</Label>
          <ProjectComboBox node={node} value={project} onChange={setProject} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-version">Version</Label>
          <Input
            id="git-version"
            placeholder="auto: short commit sha"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            className="font-mono text-xs"
            disabled={!project}
          />
        </div>
        {error && (
          <p className="font-mono text-xs text-destructive sm:col-span-2">{error}</p>
        )}
        <Button
          className="self-start"
          disabled={busy || !repo || !project || nodes.length === 0}
          onClick={submit}
        >
          <Rocket className="size-4" /> {busy ? "Cloning & building…" : "Deploy from git"}
        </Button>
      </CardContent>
    </Card>
  )
}

// ------------------------------------------------------------------ auto-deploy (webhook projects)
function AutoDeployCard() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ["projects"], queryFn: api.listProjects })
  const [editing, setEditing] = React.useState<Project | "new" | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["projects"] })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.updateProject(id, { enabled }),
    onSuccess: invalidate,
    onError: (e) => toast.error(`Update failed: ${e.message}`),
  })

  const copy = (text: string, what: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${what} copied`)
  }

  const webhookProjects = (data?.projects ?? []).filter((p) => p.deploy_source === "webhook")
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-sm font-semibold">Auto-deploy from GitHub</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            A project with a GitHub-webhook deploy mechanism auto-deploys on every push to its
            branch (version = timestamp + short sha). Configure it on the project.
          </p>
        </div>
        <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setEditing("new")}>
          <Plus className="size-3.5" /> New webhook project
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {isLoading && <Skeleton className="h-20 rounded-lg" />}
        {!isLoading && webhookProjects.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No webhook projects yet.
          </p>
        )}
        {webhookProjects.map((p) => (
          <div key={p.id} className="rounded-lg border border-border bg-secondary/30 px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <Webhook className="size-4 text-muted-foreground" />
              <span className="font-medium">{p.name}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {p.repo_url.replace(/^https:\/\//, "")} @ {p.ref}
              </span>
              <Badge variant="outline" className="font-mono text-[10px]">
                nodes {p.default_nodes.join(",")}
              </Badge>
              {p.has_token && <Badge variant="secondary" className="text-[10px]">private</Badge>}
              <div className="ml-auto flex items-center gap-1.5">
                <Switch
                  checked={p.enabled}
                  onCheckedChange={(enabled) => toggle.mutate({ id: p.id, enabled })}
                  aria-label={`Enable ${p.name}`}
                />
                <Button variant="ghost" size="icon" className="size-7"
                  aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}>
                  <Pencil className="size-3.5" />
                </Button>
              </div>
            </div>
            {p.webhook_path && (
              <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border pt-2">
                <span className="font-mono text-[11px] text-muted-foreground">
                  {window.location.origin}
                  {p.webhook_path}
                </span>
                <Button variant="outline" size="sm" className="h-6 gap-1 text-[11px]"
                  onClick={() => copy(window.location.origin + (p.webhook_path ?? ""), "Webhook URL")}>
                  <Copy className="size-3" /> URL
                </Button>
                {p.webhook_secret && (
                  <Button variant="outline" size="sm" className="h-6 gap-1 text-[11px]"
                    onClick={() => copy(p.webhook_secret ?? "", "Webhook secret")}>
                    <Copy className="size-3" /> Secret
                  </Button>
                )}
                <span className="text-[11px] text-muted-foreground">
                  GitHub → Webhooks → content type{" "}
                  <span className="font-mono">application/json</span>, events: push
                </span>
              </div>
            )}
          </div>
        ))}
      </CardContent>
      {editing && (
        <ProjectDialog
          project={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      )}
    </Card>
  )
}

// ------------------------------------------------------------------ history
const SOURCE_LABEL: Record<DeployRecord["source"], string> = {
  file: "upload",
  folder: "folder",
  git: "git",
  push: "ci push",
  webhook: "webhook",
}

function RecentDeploysCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["deploy-history"],
    queryFn: () => api.deployHistory({ perPage: 15 }),
    refetchInterval: 15_000,
  })

  const records = data?.records ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold">Recent deploys</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5">
        {isLoading && <Skeleton className="h-24 rounded-lg" />}
        {!isLoading && records.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">No deploys recorded yet.</p>
        )}
        {records.map((r) => (
          <div
            key={r.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-secondary/20 px-3 py-2"
          >
            <span className="font-mono text-[11px] text-muted-foreground">
              {fmtDateTime(r.created_at)}
            </span>
            <Badge variant="outline" className="font-mono text-[10px] uppercase">
              {SOURCE_LABEL[r.source] ?? r.source}
            </Badge>
            <span className="font-mono text-xs">
              {r.project}
              {r.version && (
                <>
                  {" @ "}
                  <Link
                    to={`/code/${encodeURIComponent(r.project)}/${encodeURIComponent(r.version)}`}
                    className="text-primary hover:underline"
                    title="View code"
                  >
                    {r.version}
                  </Link>
                </>
              )}
            </span>
            {r.actor && (
              <span className="font-mono text-[11px] text-muted-foreground">by {r.actor}</span>
            )}
            <div className="ml-auto flex items-center gap-1">
              {r.results.length > 0 ? (
                r.results.map((n) => (
                  <span
                    key={n.node}
                    title={`node ${n.node} (${n.server}): ${n.status}${n.message ? ` — ${n.message}` : ""}`}
                    className={cn(
                      "rounded-full px-2 py-0.5 font-mono text-[10px]",
                      n.status === "ok"
                        ? "bg-primary/15 text-primary"
                        : "bg-destructive/15 text-destructive",
                    )}
                  >
                    n{n.node}
                  </span>
                ))
              ) : (
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 font-mono text-[10px]",
                    r.status === "ok"
                      ? "bg-primary/15 text-primary"
                      : r.status === "pending"
                        ? "bg-secondary text-muted-foreground"
                        : "bg-destructive/15 text-destructive",
                  )}
                  title={r.message ?? undefined}
                >
                  {r.status}
                </span>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function CiTemplateCard() {
  const [origin] = React.useState(() => window.location.origin)
  const yaml = `name: deploy-spiders

on:
  push:
    tags: ["v*"]          # deploy on version tags; or use branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Build egg
        run: |
          pip install scrapyd-client
          scrapyd-deploy --build-egg=project.egg
      - name: Push to ScrapydWeb
        run: |
          curl --fail -X POST "${origin}/api/deploy/push" \\
            -H "X-Deploy-Token: \${{ secrets.SCRAPYDWEB_DEPLOY_TOKEN }}" \\
            -F "egg=@project.egg" \\
            -F "project=YOUR_PROJECT" \\
            -F "nodes=1" \\
            -F "version=\${{ github.ref_name }}"`

  return (
    <Card>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Prefer the <span className="font-mono text-xs">Auto-deploy</span> tab if this instance is
          reachable from GitHub — no CI config needed. Use this push-token workflow when you want
          the egg built in CI. 1. Set a{" "}
          <span className="font-mono text-xs">CI deploy token</span> in Settings → CI / Deploy.
          &nbsp;2. Add it to your repo as the{" "}
          <span className="font-mono text-xs">SCRAPYDWEB_DEPLOY_TOKEN</span> secret. &nbsp;3.
          Commit this workflow as{" "}
          <span className="font-mono text-xs">.github/workflows/deploy.yml</span>:
        </p>
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            className="absolute right-2 top-2 h-7 gap-1 text-xs"
            onClick={() => {
              navigator.clipboard.writeText(yaml)
              toast.success("Workflow copied")
            }}
          >
            <Copy className="size-3" /> Copy
          </Button>
          <pre className="overflow-auto rounded-lg border border-border bg-background/60 p-4 font-mono text-xs leading-relaxed">
            {yaml}
          </pre>
        </div>
        <p className="text-xs text-muted-foreground">
          The instance must be reachable from GitHub runners ({origin}).{" "}
          <span className="font-mono">nodes</span> takes a comma-separated node list. Version lands
          as the git tag — code is browsable per version on the Projects page.
        </p>
      </CardContent>
    </Card>
  )
}
